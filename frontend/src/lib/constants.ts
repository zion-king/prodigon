/** API base URL — empty string means same origin (works with Vite proxy and production nginx) */
export const API_BASE_URL = '';

/** Available models for selection */
export const MODELS = [
  { id: 'llama-3.3-70b-versatile', name: 'Llama 3.3 70B', description: 'Best quality, slower' },
  { id: 'llama-3.1-8b-instant', name: 'Llama 3.1 8B', description: 'Fast, good quality' },
  { id: 'mixtral-8x7b-32768', name: 'Mixtral 8x7B', description: 'Balanced speed & quality' },
  { id: 'openai/gpt-oss-120b', name: 'GPT-OSS 120B', description: 'High-quality, slower' },
] as const;

export const DEFAULT_MODEL = 'llama-3.3-70b-versatile';
export const DEFAULT_TEMPERATURE = 0.7;
export const DEFAULT_MAX_TOKENS = 1024;

/** Suggested prompts for the empty chat state */
export const SUGGESTED_PROMPTS = [
  'Explain microservices architecture in simple terms',
  'Write a Python function to calculate Fibonacci numbers',
  'What are the tradeoffs between REST and gRPC?',
  'How does dependency injection improve testability?',
];

/** Health polling interval in ms */
export const HEALTH_POLL_INTERVAL = 15000;

/** Job polling interval in ms */
export const JOB_POLL_INTERVAL = 2000;
