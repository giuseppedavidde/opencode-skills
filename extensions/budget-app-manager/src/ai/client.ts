export interface LlmClientLike {
  categorize(prompt: string): Promise<string>;
}

export interface StreamingLlmClient extends LlmClientLike {
  streamChat(system: string, user: string): AsyncGenerator<string>;
}
