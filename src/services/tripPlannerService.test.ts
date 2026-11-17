import { afterEach, describe, expect, it, vi } from 'vitest'
import { planTripWithProgress } from './tripPlannerService'

afterEach(() => {
  vi.unstubAllGlobals()
})

function streamResponse(chunks: string[]): Response {
  return new Response(
    new ReadableStream<Uint8Array>({
      start(controller) {
        const encoder = new TextEncoder()
        for (const chunk of chunks) controller.enqueue(encoder.encode(chunk))
        controller.close()
      },
    }),
    { status: 200, headers: { 'Content-Type': 'text/event-stream' } },
  )
}

function withSession(handler: (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>) {
  return vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    if (String(input).includes('/api/trips/session')) {
      return new Response(JSON.stringify({ csrf: 'test-csrf', expiresAt: 0, trips: 0 }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })
    }
    return handler(input, init)
  })
}

function tripCalls(mock: { mock: { calls: unknown[][] } }) {
  return mock.mock.calls.filter((call) => !String(call[0]).includes('/api/trips/session'))
}

describe('trip planner streaming', () => {
  it('propagates provider errors without issuing a second plan POST', async () => {
    const fetchMock = withSession(async () =>
      streamResponse(['data: {"type":"error","code":"places_unavailable","message":"Overpass failed"}\n\n']),
    )
    vi.stubGlobal('fetch', fetchMock)

    await expect(planTripWithProgress('test trip', null, vi.fn())).rejects.toMatchObject({
      code: 'places_unavailable',
      message: 'Overpass failed',
    })
    expect(tripCalls(fetchMock)).toHaveLength(1)
  })

  it('parses progress and success events even when split across network chunks', async () => {
    const trip = { id: 'trip_test', days: [], summary: 'ok' }
    const stream =
      'data: {"type":"progress","step":"Ищу места"}\n\n' +
      `data: ${JSON.stringify({ type: 'done', trip })}\n\n`
    const fetchMock = withSession(async () =>
      streamResponse([stream.slice(0, 18), stream.slice(18)]),
    )
    vi.stubGlobal('fetch', fetchMock)
    const progress = vi.fn()

    const result = await planTripWithProgress('test trip', null, progress)
    expect(result.id).toBe('trip_test')
    expect(progress).toHaveBeenCalledWith('Ищу места')
    expect(tripCalls(fetchMock)).toHaveLength(1)
  })

  it('does not retry when SSE ends without a done event', async () => {
    const fetchMock = withSession(async () =>
      streamResponse(['data: {"type":"progress","step":"Ищу места"}\n\n']),
    )
    vi.stubGlobal('fetch', fetchMock)

    await expect(planTripWithProgress('test trip', null, vi.fn())).rejects.toMatchObject({
      code: 'stream_interrupted',
    })
    expect(tripCalls(fetchMock)).toHaveLength(1)
  })

  it('uses the non-streaming endpoint only when the stream endpoint is unavailable', async () => {
    const trip = { id: 'trip_fallback', days: [], summary: 'ok' }
    let planCalls = 0
    const fetchMock = withSession(async () => {
      planCalls += 1
      return planCalls === 1
        ? new Response(null, { status: 404 })
        : new Response(JSON.stringify({ trip }), { status: 200 })
    })
    vi.stubGlobal('fetch', fetchMock)

    const result = await planTripWithProgress('test trip', null, vi.fn())
    expect(result.id).toBe('trip_fallback')
    expect(tripCalls(fetchMock)).toHaveLength(2)
    expect(String(tripCalls(fetchMock)[1][0])).toContain('/api/trips/plan')
  })

  it('surfaces a backend connectivity error without retrying', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      if (String(input).includes('/api/trips/session')) {
        return new Response(JSON.stringify({ csrf: 'test-csrf' }), { status: 200 })
      }
      throw new TypeError('Failed to fetch')
    })
    vi.stubGlobal('fetch', fetchMock)

    await expect(planTripWithProgress('test trip', null, vi.fn())).rejects.toMatchObject({
      code: 'network_unavailable',
    })
    expect(tripCalls(fetchMock)).toHaveLength(1)
  })
})
