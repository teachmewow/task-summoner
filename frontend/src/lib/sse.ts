export interface SseOptions<T> {
  url: string;
  eventTypes: readonly string[];
  onEvent: (event: T) => void;
  onError?: (error: Event) => void;
}

export function openSse<T>({ url, eventTypes, onEvent, onError }: SseOptions<T>): () => void {
  const source = new EventSource(url);
  const handler = (e: MessageEvent) => {
    try {
      onEvent(JSON.parse(e.data) as T);
    } catch (err) {
      console.error("SSE parse error", err);
    }
  };
  for (const type of eventTypes) source.addEventListener(type, handler);
  if (onError) source.addEventListener("error", onError);
  return () => source.close();
}
