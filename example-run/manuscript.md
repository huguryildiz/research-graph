# Does a learned channel estimator actually beat LMMSE at low SNR?

## Abstract

Reports of learned channel estimators outperforming LMMSE are common, and are
often supported by a single simulation curve with no replication count and no
uncertainty interval. We re-ask the question under a protocol frozen before
execution: twenty seed-matched replications, a stated baseline, and a paired
per-seed difference with a bootstrap interval at every reported point. The
learned estimator does beat the baseline at low SNR, by 2.09 dB at -10 dB SNR
(95% CI [1.43, 2.72], n = 20). It also beats it by more at high SNR than at low
SNR, which is the opposite of what we registered as our second hypothesis.

## Method

The channel is an eight-tap Rayleigh model with an exponentially decaying power
delay profile, observed over 64 subcarriers as noisy pilots. Within a seed, all
three estimators see the identical observation vector, so the comparison is
paired rather than independent.

The baseline is a scalar Wiener shrinkage, the LMMSE estimator under the
assumption that the frequency-domain channel taps are uncorrelated and of equal
power. The classical LMMSE estimator is the minimum-MSE linear estimator when
the true channel correlation matrix is available. Our baseline does not use that
matrix, and the Limitations section records what that costs the comparison.

The estimator we label *learned* is a tuned delay-domain filter: transform the
raw least-squares estimate to the delay domain, keep the first eight taps,
transform back, and apply Wiener shrinkage rescaled for the retained subspace.
It is not a neural network. It is the structure a learned estimator recovers in
this setting, written out explicitly so the whole benchmark stays deterministic
and inspectable. What follows therefore bounds the value of the structure, not
of any particular architecture.

Twenty seeds, 41 through 60, were fixed in the protocol before any run. The
analysis plan, the stopping rule and the Holm correction across the three
low-SNR points were fixed at the same time.

## Results

At -10 dB SNR the learned estimator lowers MSE by 2.092 dB relative to
scalar-Wiener LMMSE (95% CI [1.433, 2.716], n = 20).

At -5 dB the gain is 4.611 dB (95% CI [3.929, 5.275], n = 20), and at 0 dB SNR
the gain is 6.492 dB (95% CI [5.812, 7.163], n = 20). All three intervals
exclude zero. The registered multiplicity plan was applied to the accompanying
permutation p-values rather than to the intervals: the exact two-sided sign-flip
tests give p = 2.5e-05, 1.9e-06 and 1.9e-06, and Holm across the three
registered points leaves them at 2.5e-05, 5.7e-06 and 5.7e-06. Hypothesis h-01,
that the learned estimator attains lower MSE at or below 0 dB, is supported.

Hypothesis h-02 is not. We registered the prediction that the advantage would be
largest at the lowest SNR. Across the grid that was run, the advantage grows with
SNR rather than shrinking: 2.09 dB at -10 dB against 8.99 dB at +10 dB. The
registered analysis plan reports intervals at the three low-SNR points only, so
the +10 dB figure is a mean over the same twenty paired differences and carries
no interval here. The trend runs the other way, so the hypothesis that the
gain peaks at low SNR is not supported. We report the prediction and its failure
rather than dropping it, because it was registered before the run.

The mechanism is consistent with the direction we observed. Delay-domain
truncation removes the noise that falls outside the channel support. At low SNR
the surviving in-support noise dominates the error and the truncation buys less;
at high SNR the truncated component is a larger share of what remains.

## Limitations

The channels are synthetic. No measured channel was used, and nothing here
speaks to hardware impairments.

The baseline is scalar-Wiener LMMSE, not full-covariance LMMSE. A
full-covariance baseline knows the delay-domain structure that our learned
estimator exploits, and would narrow the reported gap, possibly to nothing. Any
reader treating these numbers as a general claim about LMMSE would be reading
past the evidence.

The SNR grid stops at -10 dB. Where the gain collapses, if it collapses, is
outside what was run.

The estimator we compare is a tuned filter, not a trained network, so nothing
here transfers automatically to a learned estimator with more capacity.

## References

- s-01 · Ye, Li, Juang — *Power of Deep Learning for Channel Estimation and Signal Detection in OFDM Systems* — IEEE Wireless Communications Letters, 2018 — doi:10.1109/lwc.2017.2757490
- s-02 · Soltani, Pourahmadi, Mirzaei, Sheikhzadeh — *Deep Learning-Based Channel Estimation* — IEEE Communications Letters, 2019 — doi:10.1109/lcomm.2019.2898944
- s-03 · Edfors, Sandell, van de Beek, Wilson, Börjesson — *OFDM channel estimation by singular value decomposition* — VTC, 1996 — doi:10.1109/vetec.1996.501446
- s-04 · Zhang, Mu, Liu, Zhang, Qian — *Deep Learning-Based Beamspace Channel Estimation in mmWave Massive MIMO Systems* — IEEE Wireless Communications Letters, 2020 — doi:10.1109/lwc.2020.3019321
