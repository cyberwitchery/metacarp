/* calls one root from each carp library; they share global and helper names */
extern void C15_alpha_x45_greet__F0_Z1_U(void);
extern void C14_beta_x45_greet__F0_Z1_U(void);

int main(void) {
  C15_alpha_x45_greet__F0_Z1_U();
  C14_beta_x45_greet__F0_Z1_U();
  return 0;
}
