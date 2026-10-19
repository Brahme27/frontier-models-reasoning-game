// Seat geometry on the table, in % of the arena box.
// seat = card centre, anchor = where coins/lines attach, speech/thought = bubble centres.
// Each seat owns one corner-ish region for its bubbles so they never collide.
export type Side = 'top' | 'right' | 'bottom' | 'left'

type Point = { x: number; y: number }

export interface SeatGeometry {
  side: Side
  seat: Point
  anchor: Point
  speech: Point
  thought: Point
}

export const SEATS: SeatGeometry[] = [
  { side: 'top', seat: { x: 50, y: 15 }, anchor: { x: 50, y: 28 }, speech: { x: 73, y: 12 }, thought: { x: 27, y: 12 } },
  { side: 'right', seat: { x: 88, y: 50 }, anchor: { x: 75, y: 50 }, speech: { x: 85, y: 29 }, thought: { x: 85, y: 73 } },
  { side: 'bottom', seat: { x: 50, y: 85 }, anchor: { x: 50, y: 72 }, speech: { x: 27, y: 88 }, thought: { x: 73, y: 88 } },
  { side: 'left', seat: { x: 12, y: 50 }, anchor: { x: 25, y: 50 }, speech: { x: 15, y: 73 }, thought: { x: 15, y: 28 } },
]

export const BANK: Point = { x: 50, y: 50 }

export function geometryFor(order: string[]): Record<string, SeatGeometry> {
  const out: Record<string, SeatGeometry> = {}
  order.forEach((id, i) => { out[id] = SEATS[i % SEATS.length] })
  return out
}
