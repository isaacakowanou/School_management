export function passageOutcomeCounts(decisions = []) {
  return decisions.reduce(
    (counts, decision) => {
      if (decision.final_decision === 'pass') counts.passed += 1
      if (decision.final_decision === 'repeat') counts.repeated += 1
      if (decision.final_decision === 'graduate') counts.graduated += 1
      return counts
    },
    { passed: 0, repeated: 0, graduated: 0 },
  )
}
