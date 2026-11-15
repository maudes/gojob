import Anthropic from "@anthropic-ai/sdk";
import { zodOutputFormat } from "@anthropic-ai/sdk/helpers/zod";
import type { z } from "zod";

export const MAIN_MODEL = process.env.MAIN_MODEL || "claude-opus-5-5";
export const REVIEWER_MODEL = process.env.REVIEWER_MODEL || "claude-haiku-5-5";

export const hasCredentials = () =>
  Boolean(process.env.ANTHROPIC_API_KEY || process.env.ANTHROPIC_AUTH_TOKEN);

let client: Anthropic | null = null;
const getClient = () => (client ??= new Anthropic());

type Effort = "low" | "medium" | "high";

export class AgentError extends Error {}

function explain(err: unknown): never {
  if (err instanceof AgentError) throw err;
  if (err instanceof Anthropic.AuthenticationError)
    throw new AgentError("The API key was rejected. Check ANTHROPIC_API_KEY in .env.local.");
  if (err instanceof Anthropic.RateLimitError)
    throw new AgentError("Rate limited by the Claude API. Wait a minute and retry.");
  if (err instanceof Anthropic.APIConnectionError)
    throw new AgentError("Could not reach the Claude API. Check your connection.");
  if (err instanceof Anthropic.APIError)
    throw new AgentError(`Claude API error ${err.status ?? ""}: ${err.message}`);
  throw err;
}

/**
 * One structured call. Current Claude models reject a `temperature` parameter, so
 * determinism for reviewers comes from low effort plus a strict schema instead.
 */
export async function runJSON<S extends z.ZodType>(opts: {
  schema: S;
  model: string;
  system: string;
  user: string;
  effort: Effort;
}): Promise<z.infer<S>> {
  try {
    const response = await getClient().messages.parse({
      model: opts.model,
      max_tokens: 16000,
      system: opts.system,
      messages: [{ role: "user", content: opts.user }],
      output_config: { format: zodOutputFormat(opts.schema), effort: opts.effort },
    });
    if (response.stop_reason === "refusal")
      throw new AgentError("The model declined this request.");
    if (response.stop_reason === "max_tokens")
      throw new AgentError("The answer was cut off before it finished. Retry.");
    if (response.parsed_output == null)
      throw new AgentError("The model returned output that did not match the expected structure.");
    return response.parsed_output as z.infer<S>;
  } catch (err) {
    explain(err);
  }
}

/** A long free-text call that may search the web. Returns the concatenated text. */
export async function runWithSearch(opts: {
  system: string;
  user: string;
  maxSearches: number;
  maxTokens: number;
}): Promise<string> {
  try {
    const messages: Anthropic.MessageParam[] = [{ role: "user", content: opts.user }];
    for (let turn = 0; turn < 6; turn++) {
      const stream = getClient().messages.stream({
        model: MAIN_MODEL,
        max_tokens: opts.maxTokens,
        system: opts.system,
        messages,
        tools: [{ type: "web_search_20260209", name: "web_search", max_uses: opts.maxSearches }],
        output_config: { effort: "medium" },
      });
      const message = await stream.finalMessage();
      if (message.stop_reason === "refusal")
        throw new AgentError("The model declined this request.");
      if (message.stop_reason === "pause_turn") {
        messages.push({ role: "assistant", content: message.content });
        continue;
      }
      if (message.stop_reason === "max_tokens")
        throw new AgentError("The answer was cut off before it finished. Retry.");
      return message.content
        .filter((b): b is Anthropic.TextBlock => b.type === "text")
        .map((b) => b.text)
        .join("");
    }
    throw new AgentError("The research run did not finish. Retry.");
  } catch (err) {
    explain(err);
  }
}
