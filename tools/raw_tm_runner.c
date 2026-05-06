#include <stdio.h>
#include <stdlib.h>
#include <time.h>

/*
 * Generic fixed-array runner for lowered raw TM artifacts.
 *
 * The generated header supplies one artifact-specific raw transition table as
 * dense (state, read-symbol) arrays plus the initial .utm.band runtime tape.
 * This executes the real lowered raw transitions, unlike the MetaASM C runner
 * which shortcuts directly to the universal MetaASM algorithm.
 *
 * Useful first checks:
 * - Run an L1 UTM .tm over its L1 band and confirm the incrementer reaches 1100.
 * - Run a wider L2 UTM .tm over the narrower L1 band and confirm ABI-lattice
 *   compatibility still reaches 1100.
 *
 * Limitations:
 * - The tape is fixed-size with generated blank margin.
 * - The generated header is artifact-specific.
 * - This is still a raw transition runner; a full L2-band run may need an
 *   enormous transition budget even though dispatch itself is fast.
 */

#include "raw_tm_runner_data.h"

static long long parse_max_steps(int argc, char **argv) {
  if (argc < 2) {
    return -1;
  }
  char *end = NULL;
  long long value = strtoll(argv[1], &end, 10);
  if (end == argv[1] || *end != '\0' || value < 0) {
    fprintf(stderr, "usage: %s [max_steps]\n", argv[0]);
    exit(2);
  }
  return value;
}

static int *init_tape(void) {
  int *tape = malloc(sizeof(int) * TAPE_SIZE);
  if (tape == NULL) {
    fprintf(stderr, "failed to allocate tape\n");
    exit(2);
  }
  for (int i = 0; i < TAPE_SIZE; i++) {
    tape[i] = BLANK;
  }
  for (int i = 0; i < INIT_COUNT; i++) {
    tape[INIT[i][0]] = INIT[i][1];
  }
  return tape;
}

static int decode_source_symbol(const int *tape, int bits_start) {
  int value = 0;
  for (int i = 0; i < SOURCE_SYMBOL_WIDTH; i++) {
    int token = tape[bits_start + i];
    if (token == TOK_0) {
      value = value << 1;
    } else if (token == TOK_1) {
      value = (value << 1) | 1;
    } else {
      return -1;
    }
  }
  return value;
}

static void dump_decoded_right_tape(const int *tape) {
  printf("decoded_right:");
  int raw = 0;
  int cells = 0;
  while (raw < RIGHT_TOKEN_COUNT && cells < RIGHT_DUMP_CELLS) {
    int address = raw + ORIGIN;
    if (address + 2 + SOURCE_SYMBOL_WIDTH >= TAPE_SIZE || tape[address] != TOK_CELL) {
      raw++;
      continue;
    }
    int symbol_id = decode_source_symbol(tape, address + 2);
    if (symbol_id >= 0 && symbol_id < SOURCE_SYMBOL_COUNT) {
      printf(" %s", SOURCE_SYMBOLS[symbol_id]);
    } else {
      printf(" <bad-symbol-%d>", symbol_id);
    }
    raw += 3 + SOURCE_SYMBOL_WIDTH;
    cells++;
  }
  printf("\n");
}

static void dump_raw_right_tape(const int *tape) {
  if (RAW_DUMP_CELLS <= 0) {
    return;
  }
  printf("raw_right:");
  for (int raw = 0; raw < RAW_DUMP_CELLS; raw++) {
    int address = raw + ORIGIN;
    if (address < 0 || address >= TAPE_SIZE) {
      printf(" <out>");
    } else {
      printf(" %s", SYMBOLS[tape[address]]);
    }
  }
  printf("\n");
}

int main(int argc, char **argv) {
  long long max_steps = parse_max_steps(argc, argv);
  int *tape = init_tape();
  int state = START_STATE;
  int head = START_HEAD;
  long long steps = 0;
  clock_t start_clock = clock();

  while (state != HALT) {
    if (max_steps >= 0 && steps >= max_steps) {
      double seconds = (double)(clock() - start_clock) / CLOCKS_PER_SEC;
      printf("status=fuel_exhausted steps=%lld head=%d raw_head=%d state=%s seconds=%.6f msteps_per_s=%.3f\n",
             steps, head, head - ORIGIN, STATES[state], seconds, seconds > 0 ? (steps / seconds) / 1000000.0 : 0.0);
      dump_decoded_right_tape(tape);
      dump_raw_right_tape(tape);
      free(tape);
      return 0;
    }
    if (head < 0 || head >= TAPE_SIZE) {
      fprintf(stderr, "head out of range: head=%d raw_head=%d steps=%lld state=%s\n",
              head, head - ORIGIN, steps, STATES[state]);
      free(tape);
      return 3;
    }

    int read = tape[head];
    int offset = state * SYMBOL_COUNT + read;
    int next = NEXT_TABLE[offset];
    if (next < 0) {
      fprintf(stderr, "stuck state=%s read=%s head=%d raw_head=%d steps=%lld\n",
              STATES[state], SYMBOLS[read], head, head - ORIGIN, steps);
      dump_decoded_right_tape(tape);
      dump_raw_right_tape(tape);
      free(tape);
      return 4;
    }
    tape[head] = WRITE_TABLE[offset];
    state = next;
    head += MOVE_TABLE[offset];
    steps++;
  }

  double seconds = (double)(clock() - start_clock) / CLOCKS_PER_SEC;
  printf("status=halted steps=%lld head=%d raw_head=%d state=%s seconds=%.6f msteps_per_s=%.3f\n",
         steps, head, head - ORIGIN, STATES[state], seconds, seconds > 0 ? (steps / seconds) / 1000000.0 : 0.0);
  dump_decoded_right_tape(tape);
  dump_raw_right_tape(tape);
  free(tape);
  return 0;
}
