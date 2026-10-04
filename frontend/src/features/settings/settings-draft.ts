import type {
  AppSettings,
  AssessmentScoreWeights,
} from "../../lib/types/api.ts";

export function settingsChanges(
  saved: AppSettings,
  draft: AppSettings,
): Partial<AppSettings> {
  const changes: Partial<AppSettings> = {};
  for (const key of Object.keys(saved) as Array<keyof AppSettings>) {
    if (JSON.stringify(saved[key]) !== JSON.stringify(draft[key])) {
      Object.assign(changes, { [key]: draft[key] });
    }
  }
  return changes;
}

export function normalizedWeights(
  source: AssessmentScoreWeights,
): AssessmentScoreWeights {
  const weights = structuredClone(source);
  for (const group of Object.keys(weights) as Array<
    keyof AssessmentScoreWeights
  >) {
    const values = weights[group] as Record<string, number>;
    const total = Object.values(values).reduce((sum, value) => sum + value, 0);
    if (total > 0)
      for (const key of Object.keys(values))
        values[key] = (values[key] / total) * 100;
  }
  return weights;
}
