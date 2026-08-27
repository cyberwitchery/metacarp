/* The registered C primitive examples/simple.carp declares. Non-static so the
   symbol is exported from the test binary and MCJIT's process-symbol resolver
   can bind the JIT'd module's `int_inc` declaration to it, the way a linked
   build would resolve it at link time. */
int int_inc(int x) { return x + 1; }

/* Registered primitives for the nominal-tier test program. */
bool lt(int a, int b) { return a < b; }
int add(int a, int b) { return a + b; }

/* Mirrors of the C backend's sum-type layout for the nominal test types,
   with size/offset probes the layout-parity assertions compare against the
   LLVM backend's data-layout computations. */
#include <stddef.h>
#include <stdbool.h>

typedef struct {
  union {
    struct { bool member_0; int member_1; } variant_0;
    struct { unsigned char unused; } variant_1;
  } data;
  int tag;
} CSignal;

typedef struct {
  union {
    struct { int member_0; } variant_0;
    struct { unsigned char unused; } variant_1;
  } data;
  int tag;
} CInner;

typedef struct {
  union {
    struct { CInner member_0; } variant_0;
    struct { unsigned char unused; } variant_1;
  } data;
  int tag;
} COuter;

#include <string.h>
int strlen_of(char** s) { return (int)strlen(*s); }

/* Owned-string primitives for the managed tier: plain malloc/free so the
   symbols are exported from the test binary regardless of how the Carp
   runtime defines its own String functions. */
char* carp_llvm_str_copy(char** s) {
  size_t n = strlen(*s);
  char* out = malloc(n + 1);
  memcpy(out, *s, n + 1);
  return out;
}
void carp_llvm_str_delete(char* s) { free(s); }
int carp_llvm_str_len(char** s) { return (int)strlen(*s); }

/* Array-tier primitives; `Array` comes from the Carp runtime headers the
   generated main.c includes before this file. */
int total3(Array* a) {
  int sum = 0;
  for (size_t i = 0; i < a->len; i++) sum += ((int*)a->data)[i];
  return sum;
}
int deref_int(int* p) { return *p; }

int c_signal_size(void) { return (int)sizeof(CSignal); }
int c_signal_tag_offset(void) { return (int)offsetof(CSignal, tag); }
int c_outer_size(void) { return (int)sizeof(COuter); }
int c_outer_tag_offset(void) { return (int)offsetof(COuter, tag); }
