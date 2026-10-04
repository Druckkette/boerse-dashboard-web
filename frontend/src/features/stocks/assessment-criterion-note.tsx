import { assessmentCriteria } from "./assessment-criteria";

export function AssessmentCriterionNote({
  criterion,
  id,
}: {
  criterion: string;
  id?: string;
}) {
  const note = assessmentCriteria[criterion]?.note;
  if (!note) return null;
  return (
    <details id={id} className="mt-1 text-xs leading-5 text-[#687386]">
      <summary className="cursor-pointer text-[#0f766e]">
        Bestandteile und Berechnung
      </summary>
      <p className="mt-1">{note}</p>
    </details>
  );
}
