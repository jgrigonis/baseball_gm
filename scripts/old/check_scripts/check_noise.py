import random

seed = 68

rng = random.Random(seed)
samples = [rng.gauss(0, 1.6) for _ in range(20)]
print(f"Mean of 20 draws: {sum(samples) / len(samples):.3f}")  # won't be 0.0

# vs large sample
rng2 = random.Random(seed)
samples2 = [rng2.gauss(0, 1.6) for _ in range(100_000)]
print(f"Mean of 100k draws: {sum(samples2) / len(samples2):.4f}")  # very close to 0.0
