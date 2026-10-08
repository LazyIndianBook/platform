// When to try again after a 429, as the design says it ("You can try again at 18:24"): the time in India that many
// seconds from now. The API says how long in its Retry-After header, or only in DRF's words ("Request was throttled.
// Expected available in 1800 seconds."): secondsIn() reads those. Server pages and the contact form share it.

export function secondsIn(message: string): number {
  return Number(/(\d+) seconds?/.exec(message)?.[1]) || 60;
}

export function retryAt(seconds: number, now = Date.now()): string {
  return new Intl.DateTimeFormat("en-IN", {
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
    timeZone: "Asia/Kolkata",
  }).format(now + seconds * 1000);
}
