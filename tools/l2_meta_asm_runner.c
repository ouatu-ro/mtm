#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/*
 * Fast fixed-array runner for L2 through the MetaASM universal-machine logic.
 *
 * This runner executes the same block-level algorithm produced by
 * build_universal_meta_asm(): START_STEP, FIND_HEAD, LOOKUP_RULE,
 * MATCHED_RULE, and the move dispatch blocks. The generated header supplies the
 * L2 .utm.band as integer token arrays plus precomputed offsets for registers,
 * rules, and simulated tape cells.
 *
 * What this proves:
 * - The L2 band can be interpreted by the universal MetaASM semantics.
 * - For the incrementer artifact, the L2 MetaASM run halts after simulating the
 *   full L1 raw run and leaves the encoded L1 tape for 1100.
 *
 * What this does not prove:
 * - It does not execute the lowered L2 raw transition table.
 * - It is not a general replacement for mtm.meta_asm_host; it is specialized to
 *   the generated fixed-array layout.
 *
 * Limitations:
 * - Dynamic simulated-tape extension exits with an error. The current
 *   incrementer L2 run stays within the precomputed cells.
 * - It has no trace/debug output beyond counters and a final right-band dump.
 * - The header is artifact-specific and must be regenerated for each L2 band.
 */

#include "l2_meta_asm_data.h"

enum {
  SIDE_LEFT = 0,
  SIDE_RIGHT = 1,
};

enum {
  START_STEP = 0,
  FIND_HEAD,
  LOOKUP_RULE,
  CHECK_STATE,
  CHECK_READ,
  NEXT_RULE,
  MATCHED_RULE,
  DISPATCH_MOVE,
  CHECK_RIGHT,
  MOVE_LEFT,
  MOVE_RIGHT,
  HALT_LABEL,
  STUCK_LABEL,
};

static int left_band[LEFT_CAP];
static int right_band[RIGHT_CAP];
static int cmp_flag = 0;
static int label = START_STEP;
static int pc = 0;
static int current_rule = 0;
static int sim_side = SIM_SIDE_INIT;
static int sim_cell = SIM_CELL_INIT;
static long long meta_steps = 0;
static long long guest_steps = 0;

static long long parse_limit(int argc, char **argv) {
  if (argc < 2) {
    return 1000000;
  }
  char *end = NULL;
  long long value = strtoll(argv[1], &end, 10);
  if (end == argv[1] || *end != '\0' || value < 0) {
    fprintf(stderr, "usage: %s [meta_instruction_limit]\n", argv[0]);
    exit(2);
  }
  return value;
}

static void init_bands(void) {
  memcpy(left_band, LEFT_INIT, sizeof(int) * LEFT_LEN);
  memcpy(right_band, RIGHT_INIT, sizeof(int) * RIGHT_LEN);
}

static int bits_equal_literal(int start, const int *bits, int width) {
  for (int i = 0; i < width; i++) {
    if (left_band[start + i] != bits[i]) {
      return 0;
    }
  }
  return 1;
}

static int bits_equal_left(int left_start, int right_start, int width) {
  for (int i = 0; i < width; i++) {
    if (left_band[left_start + i] != left_band[right_start + i]) {
      return 0;
    }
  }
  return 1;
}

static void copy_left_field(int dst, int src, int width) {
  for (int i = 0; i < width; i++) {
    left_band[dst + i] = left_band[src + i];
  }
}

static int head_symbol_start(void) {
  if (sim_side == SIDE_LEFT) {
    return LEFT_CELL_STARTS[sim_cell] + 2;
  }
  return RIGHT_CELL_STARTS[sim_cell] + 2;
}

static void copy_head_symbol_to_cur_symbol(void) {
  int start = head_symbol_start();
  if (sim_side == SIDE_LEFT) {
    for (int i = 0; i < SYMBOL_WIDTH; i++) {
      left_band[G_CUR_SYMBOL + i] = left_band[start + i];
    }
  } else {
    for (int i = 0; i < SYMBOL_WIDTH; i++) {
      left_band[G_CUR_SYMBOL + i] = right_band[start + i];
    }
  }
}

static void copy_write_symbol_to_head(void) {
  int start = head_symbol_start();
  if (sim_side == SIDE_LEFT) {
    for (int i = 0; i < SYMBOL_WIDTH; i++) {
      left_band[start + i] = left_band[G_WRITE_SYMBOL + i];
    }
  } else {
    for (int i = 0; i < SYMBOL_WIDTH; i++) {
      right_band[start + i] = left_band[G_WRITE_SYMBOL + i];
    }
  }
}

static void move_sim_head_left(void) {
  if (sim_side == SIDE_RIGHT) {
    right_band[RIGHT_CELL_STARTS[sim_cell] + 1] = TOK_NO_HEAD;
    if (sim_cell > 0) {
      sim_cell--;
      right_band[RIGHT_CELL_STARTS[sim_cell] + 1] = TOK_HEAD;
      return;
    }
    if (LEFT_CELL_COUNT == 0) {
      fprintf(stderr, "left tape extension is not implemented in this fast runner\n");
      exit(5);
    }
    sim_side = SIDE_LEFT;
    sim_cell = LEFT_CELL_COUNT - 1;
    left_band[LEFT_CELL_STARTS[sim_cell] + 1] = TOK_HEAD;
    return;
  }

  left_band[LEFT_CELL_STARTS[sim_cell] + 1] = TOK_NO_HEAD;
  if (sim_cell == 0) {
    fprintf(stderr, "left tape extension is not implemented in this fast runner\n");
    exit(5);
  }
  sim_cell--;
  left_band[LEFT_CELL_STARTS[sim_cell] + 1] = TOK_HEAD;
}

static void move_sim_head_right(void) {
  if (sim_side == SIDE_LEFT) {
    left_band[LEFT_CELL_STARTS[sim_cell] + 1] = TOK_NO_HEAD;
    if (sim_cell + 1 < LEFT_CELL_COUNT) {
      sim_cell++;
      left_band[LEFT_CELL_STARTS[sim_cell] + 1] = TOK_HEAD;
      return;
    }
    if (RIGHT_CELL_COUNT == 0) {
      fprintf(stderr, "right tape extension is not implemented in this fast runner\n");
      exit(5);
    }
    sim_side = SIDE_RIGHT;
    sim_cell = 0;
    right_band[RIGHT_CELL_STARTS[sim_cell] + 1] = TOK_HEAD;
    return;
  }

  right_band[RIGHT_CELL_STARTS[sim_cell] + 1] = TOK_NO_HEAD;
  if (sim_cell + 1 >= RIGHT_CELL_COUNT) {
    fprintf(stderr, "right tape extension is not implemented in this fast runner\n");
    exit(5);
  }
  sim_cell++;
  right_band[RIGHT_CELL_STARTS[sim_cell] + 1] = TOK_HEAD;
}

static void step_meta_instruction(void) {
  meta_steps++;

  switch (label) {
    case START_STEP:
      if (pc == 0) {
        cmp_flag = bits_equal_literal(G_CUR_STATE, HALT_BITS, STATE_WIDTH);
        pc = 1;
      } else {
        label = cmp_flag ? HALT_LABEL : FIND_HEAD;
        pc = 0;
      }
      return;

    case FIND_HEAD:
      if (pc == 0) {
        pc = 1;
      } else if (pc == 1) {
        copy_head_symbol_to_cur_symbol();
        pc = 2;
      } else if (pc == 2) {
        current_rule = 0;
        pc = 3;
      } else {
        label = LOOKUP_RULE;
        pc = 0;
      }
      return;

    case LOOKUP_RULE:
      label = current_rule >= RULE_COUNT ? STUCK_LABEL : CHECK_STATE;
      pc = 0;
      return;

    case CHECK_STATE:
      if (pc == 0) {
        cmp_flag = bits_equal_left(G_CUR_STATE, RULE_STATE_START[current_rule], STATE_WIDTH);
        pc = 1;
      } else {
        label = cmp_flag ? CHECK_READ : NEXT_RULE;
        pc = 0;
      }
      return;

    case CHECK_READ:
      if (pc == 0) {
        cmp_flag = bits_equal_left(G_CUR_SYMBOL, RULE_READ_START[current_rule], SYMBOL_WIDTH);
        pc = 1;
      } else {
        label = cmp_flag ? MATCHED_RULE : NEXT_RULE;
        pc = 0;
      }
      return;

    case NEXT_RULE:
      if (pc == 0) {
        current_rule++;
        pc = 1;
      } else {
        label = LOOKUP_RULE;
        pc = 0;
      }
      return;

    case MATCHED_RULE:
      if (pc == 0) {
        copy_left_field(G_WRITE_SYMBOL, RULE_WRITE_START[current_rule], SYMBOL_WIDTH);
        pc = 1;
      } else if (pc == 1) {
        copy_left_field(G_NEXT_STATE, RULE_NEXT_START[current_rule], STATE_WIDTH);
        pc = 2;
      } else if (pc == 2) {
        copy_left_field(G_MOVE_DIR, RULE_MOVE_START[current_rule], DIR_WIDTH);
        pc = 3;
      } else if (pc == 3) {
        pc = 4;
      } else if (pc == 4) {
        copy_write_symbol_to_head();
        pc = 5;
      } else if (pc == 5) {
        copy_left_field(G_CUR_STATE, G_NEXT_STATE, STATE_WIDTH);
        pc = 6;
      } else if (pc == 6) {
        cmp_flag = bits_equal_literal(G_CUR_STATE, HALT_BITS, STATE_WIDTH);
        pc = 7;
      } else {
        label = DISPATCH_MOVE;
        pc = 0;
      }
      return;

    case DISPATCH_MOVE:
      if (pc == 0) {
        cmp_flag = bits_equal_literal(G_MOVE_DIR, LEFT_BITS, DIR_WIDTH);
        pc = 1;
      } else {
        label = cmp_flag ? MOVE_LEFT : CHECK_RIGHT;
        pc = 0;
      }
      return;

    case CHECK_RIGHT:
      if (pc == 0) {
        cmp_flag = bits_equal_literal(G_MOVE_DIR, RIGHT_BITS, DIR_WIDTH);
        pc = 1;
      } else {
        if (cmp_flag) {
          label = MOVE_RIGHT;
        } else {
          guest_steps++;
          label = START_STEP;
        }
        pc = 0;
      }
      return;

    case MOVE_LEFT:
      if (pc == 0) {
        pc = 1;
      } else if (pc == 1) {
        move_sim_head_left();
        guest_steps++;
        pc = 2;
      } else {
        label = START_STEP;
        pc = 0;
      }
      return;

    case MOVE_RIGHT:
      if (pc == 0) {
        pc = 1;
      } else if (pc == 1) {
        move_sim_head_right();
        guest_steps++;
        pc = 2;
      } else {
        label = START_STEP;
        pc = 0;
      }
      return;

    case HALT_LABEL:
      label = HALT_LABEL;
      pc = -1;
      return;

    case STUCK_LABEL:
      label = STUCK_LABEL;
      pc = -1;
      return;
  }
}

static int bits_to_int_from_right_cell(int cell, int width) {
  int start = RIGHT_CELL_STARTS[cell] + 2;
  int value = 0;
  for (int i = 0; i < width; i++) {
    value = (value << 1) | (right_band[start + i] == TOK_1);
  }
  return value;
}

int main(int argc, char **argv) {
  long long limit = parse_limit(argc, argv);
  init_bands();

  while (meta_steps < limit && pc >= 0) {
    step_meta_instruction();
  }

  const char *status = "fuel_exhausted";
  if (pc < 0 && label == HALT_LABEL) {
    status = "halted";
  } else if (pc < 0 && label == STUCK_LABEL) {
    status = "stuck";
  }

  printf("status=%s meta_steps=%lld guest_steps=%lld label=%d pc=%d rule=%d sim_side=%d sim_cell=%d\n",
         status, meta_steps, guest_steps, label, pc, current_rule, sim_side, sim_cell);

  int dump_cells = RIGHT_CELL_COUNT < 48 ? RIGHT_CELL_COUNT : 48;
  printf("right_symbols:");
  for (int i = 0; i < dump_cells; i++) {
    int symbol_id = bits_to_int_from_right_cell(i, SYMBOL_WIDTH);
    if (symbol_id >= 0 && symbol_id < SOURCE_SYMBOL_COUNT) {
      printf(" %s", SOURCE_SYMBOLS[symbol_id]);
    } else {
      printf(" <bad-symbol-%d>", symbol_id);
    }
  }
  printf("\n");

  return 0;
}
