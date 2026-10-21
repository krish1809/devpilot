import { describe, expect, it } from "vitest";

import { createSseParser, type SseMessage } from "./sse";

function parse(chunks: string[]): SseMessage[] {
  const messages: SseMessage[] = [];
  const feed = createSseParser((m) => messages.push(m));
  chunks.forEach(feed);
  return messages;
}

describe("createSseParser", () => {
  it("parses an event with data", () => {
    expect(parse(['event: run\ndata: {"id":1}\n\n'])).toEqual([
      { event: "run", data: '{"id":1}' },
    ]);
  });

  it("reassembles frames split across network chunks", () => {
    expect(parse(["event: ru", 'n\ndata: {"i', 'd":1}\n', "\n"])).toEqual([
      { event: "run", data: '{"id":1}' },
    ]);
  });

  it("ignores retry hints and keep-alive comments, and joins multi-line data", () => {
    expect(parse(["retry: 3000\n\n: keep-alive\n\nevent: run\ndata: a\ndata: b\n\n"])).toEqual([
      { event: "run", data: "a\nb" },
    ]);
  });

  it("defaults the event name and accepts CRLF line endings", () => {
    expect(parse(["data: x\r\n\r\n"])).toEqual([{ event: "message", data: "x" }]);
  });

  it("does not emit a frame until its terminating blank line arrives", () => {
    expect(parse(["event: run\ndata: x\n"])).toEqual([]);
  });
});
