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

describe('trip planner streaming', () => {
  it('propagates provider errors without issuing a second plan POST', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      streamResponse(['data: {"type":"error","code":"places_unavailable","message":"Overpass failed"}\n\n']),
    )
    vi.stubGlobal('fetch', fetchMock)

    await expect(planTripWithProgress('test trip', null, vi.fn())).rejects.toMatchObject({
      code: 'places_unavailable',
      message: 'Overpass failed',
    })
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('parses progress and success events even when split across network chunks', async () => {
    const trip = { id: 'trip_test', days: [], summary: 'ok' }
    const stream =
      'data: {"type":"progress","step":"Ищу места"}\n\n' +
      `data: ${JSON.stringify({ type: 'done', trip })}\n\n`
    const fetchMock = vi.fn().mockResolvedValue(streamResponse([stream.slice(0, 18), stream.slice(18)]))
    vi.stubGlobal('fetch', fetchMock)
    const progress = vi.fn()

    const result = await planTripWithProgress('test trip', null, progress)
    expect(result.id).toBe('trip_test')
    expect(progress).toHaveBeenCalledWith('Ищу места')
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('does not retry when SSE ends without a done event', async () => {
    const fetchMock = vi.fn().mockResolvedValue(streamResponse(['data: {"type":"progress","step":"Ищу места"}\n\n']))
    vi.stubGlobal('fetch', fetchMock)

    await expect(planTripWithProgress('test trip', null, vi.fn())).rejects.toMatchObject({
      code: 'stream_interrupted',
    })
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('uses the non-streaming endpoint only when the stream endpoint is unavailable', async () => {
    const trip = { id: 'trip_fallback', days: [], summary: 'ok' }
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(null, { status: 404 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ trip }), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)

    const result = await planTripWithProgress('test trip', null, vi.fn())
    expect(result.id).toBe('trip_fallback')
    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(String(fetchMock.mock.calls[1][0])).toContain('/api/trips/plan')
  })

  it('surfaces a backend connectivity error without retrying', async () => {
    const fetchMock = vi.fn().mockRejectedValue(new TypeError('Failed to fetch'))
    vi.stubGlobal('fetch', fetchMock)

    await expect(planTripWithProgress('test trip', null, vi.fn())).rejects.toMatchObject({
      code: 'network_unavailable',
    })
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })
})
