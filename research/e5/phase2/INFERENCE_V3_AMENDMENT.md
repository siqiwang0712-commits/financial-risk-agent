# Pre-outcome paired-null repair

Phase-II's complete V2 probe discovered additional coverage noninferiority
anti-conservatism: 569/5000 rejections at N=100 and 336/5000 at N=500 under
nested automated decisions with true coverage difference -0.05. The one-sided
99% exact lower bounds exceed 0.05. See qualification/v2_nested_ni_probe.json.
This failure is separate from the preserved original absolute-coverage failure.

V3 keeps V2's boundary Bernoulli absolute test, paired company BCa intervals,
the frozen utility margins, IUT maximum, and Holm family control. It replaces
residual-centered error and coverage-NI null sampling with a constrained
trinomial company null whose mean equals the tested boundary. The error test
conditions on the frozen VERIFIED company subset, preserving its common
observed denominator. The shared empirical bootstrap resamples all arms and
observability together. Undefined components cannot yield primary success.

This is a new analysis identity, not a claim that V2 qualified. No E5 outcomes
or predictions have been opened or generated. V3 cannot analyze E5 until its
full canonical simulation qualification passes with the exact code hashes.
