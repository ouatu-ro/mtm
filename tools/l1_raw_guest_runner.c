#include <stdio.h>
#include <stdlib.h>

/*
 * Fast fixed-array runner for the L1 raw guest computation.
 *
 * This is not a universal-machine interpreter and it is not the real L2 raw TM.
 * It runs the L1 raw transition table directly over the L1 runtime tape encoded
 * into l1_raw_guest_data.h. Its purpose is a cheap sanity check for the guest
 * computation that L2 will encode: for the incrementer, the run should halt with
 * the L1 encoded tape for 1100.
 *
 * Limitations:
 * - The generated header is artifact-specific.
 * - The tape is a fixed-size array with a generated blank margin.
 * - This does not prove L2 MetaASM or lowered L2 raw execution.
 */

typedef struct {
  int state;
  int read;
  int next;
  int write;
  int move;
} Rule;

#include "l1_raw_guest_data.h"

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

int main(int argc, char **argv) {
  long long max_steps = parse_max_steps(argc, argv);
  int *tape = malloc(sizeof(int) * TAPE_SIZE);
  if (tape == NULL) {
    fprintf(stderr, "failed to allocate tape\n");
    return 2;
  }

  for (int i = 0; i < TAPE_SIZE; i++) {
    tape[i] = BLANK;
  }
  for (int i = 0; i < INIT_COUNT; i++) {
    tape[INIT[i][0]] = INIT[i][1];
  }

  int state = START_STATE;
  int head = START_HEAD;
  long long steps = 0;

  while (state != HALT) {
    if (max_steps >= 0 && steps >= max_steps) {
      printf("status=fuel_exhausted steps=%lld head=%d raw_head=%d\n", steps, head, head - ORIGIN);
      free(tape);
      return 0;
    }
    if (head < 0 || head >= TAPE_SIZE) {
      fprintf(stderr, "head out of range: head=%d raw_head=%d steps=%lld\n", head, head - ORIGIN, steps);
      free(tape);
      return 3;
    }

    int read = tape[head];
    int found = 0;
    for (int i = 0; i < RULE_COUNT; i++) {
      Rule rule = RULES[i];
      if (rule.state == state && rule.read == read) {
        tape[head] = rule.write;
        state = rule.next;
        head += rule.move;
        steps++;
        found = 1;
        break;
      }
    }

    if (!found) {
      fprintf(stderr, "stuck state=%d read=%s head=%d raw_head=%d steps=%lld\n", state, SYMBOLS[read], head, head - ORIGIN, steps);
      free(tape);
      return 4;
    }
  }

  printf("status=halted steps=%lld head=%d raw_head=%d\n", steps, head, head - ORIGIN);
  for (int raw = 0; raw < RIGHT_DUMP_CELLS; raw++) {
    printf("%d:%s\n", raw, SYMBOLS[tape[raw + ORIGIN]]);
  }

  free(tape);
  return 0;
}
