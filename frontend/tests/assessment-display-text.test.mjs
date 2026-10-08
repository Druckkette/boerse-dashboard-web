import assert from 'node:assert/strict';
import test from 'node:test';
import { assessmentDisplayText } from '../src/features/stocks/assessment-display-text.ts';

test('comparison wording keeps inclusive and strict thresholds distinct', () => {
  assert.equal(assessmentDisplayText('RS >=80 · ROE ≥17% · ATR <=4% · Beta ≤2'), 'RS mindestens 80 · ROE mindestens 17% · ATR höchstens 4% · Beta höchstens 2');
  assert.equal(assessmentDisplayText('EPS >0 · Preis <$15'), 'EPS mehr als 0 · Preis weniger als $15');
});
test('chart shorthand expands while periods, signed growth and narrative text stay intact', () => {
  assert.equal(assessmentDisplayText('21>50>200'), '21-Tage-Linie über 50-Tage-Linie über 200-Tage-Linie');
  assert.equal(assessmentDisplayText('4 vs 1 (20T) · 1 in 10T · hohes Vol.'), '4 gegenüber 1 (20 Handelstage) · 1 in 10 Handelstagen · hohes Volumen');
  assert.equal(assessmentDisplayText('2026 Q3 -14.5% · Vorjahr fehlt'), '2026 Q3 -14.5% · Vorjahr fehlt');
});
