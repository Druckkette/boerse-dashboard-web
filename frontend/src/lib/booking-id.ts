/** Random booking identity also available on the NAS's HTTP LAN origin. */
export function createBookingId(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  return Array.from(bytes, value => value.toString(16).padStart(2, "0")).join("");
}
