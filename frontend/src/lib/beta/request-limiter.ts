// Limit bursts from many panels in one browser; backend admission remains authoritative.
export function createRequestLimiter(maximum: number, maxWaiting = 32) {
  let active = 0;
  const waiting: (() => void)[] = [];
  return async function run<T>(operation: () => Promise<T>): Promise<T> {
    if (active >= maximum) {
      if (waiting.length >= maxWaiting) throw new Error("Zu viele gleichzeitige Ansichten. Bitte kurz warten.");
      await new Promise<void>(resolve => waiting.push(resolve));
    } else active++;
    try { return await operation(); }
    finally {
      const next = waiting.shift();
      if (next) next(); else active--;
    }
  };
}
let betaBrowser = false;
const betaRequests = createRequestLimiter(1);
export function configureBetaApiRequests(beta: boolean) { betaBrowser = beta; }
export function withApiSlot<T>(operation: () => Promise<T>) {
  return betaBrowser ? betaRequests(operation) : operation();
}
