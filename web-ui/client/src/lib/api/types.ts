export const ENDPOINT_STATUSES = [
  'Connected',
  'Unreachable',
  'Unauthorized',
  'Not configured'
] as const;

export type EndpointStatus = (typeof ENDPOINT_STATUSES)[number];

export type MessageKind =
  | 'user_text'
  | 'ai_text'
  | 'user_speech'
  | 'ai_speech'
  | 'call_start'
  | 'call_end';

export type MessageRole = 'user' | 'assistant' | 'system' | 'event';

export type MessageAlternateSourceAction = 'first_mes' | 'regenerate' | 'swipe' | 'continue';

export interface MessageAlternate {
  id: string;
  message_id: string;
  alternate_index: number;
  content_text: string;
  source_action: MessageAlternateSourceAction;
  created_at?: string | null;
}

export interface ThreadMessage {
  id: string;
  thread_id: string;
  message_kind: MessageKind;
  role: MessageRole;
  sequence: number;
  content_text: string | null;
  selected_alternate_id: string | null;
  alternates: MessageAlternate[];
  stale_after_edit: boolean;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface CharacterPortraitMetadata {
  portrait_url?: string | null;
  portrait_path?: string | null;
  portrait_asset_id?: string | null;
  portrait_storage_path?: string | null;
  portrait_mime_type?: string | null;
  portrait_size_bytes?: number | null;
  portrait_updated_at?: string | null;
}

export interface CharacterBaseFields {
  name: string;
  description?: string | null;
  personality?: string | null;
  scenario?: string | null;
  first_mes?: string | null;
  mes_example?: string | null;
  system_prompt?: string | null;
  creator_notes?: string | null;
  character_notes?: string | null;
  tags?: string[];
  alternate_greetings?: string[];
  post_history_instructions?: string | null;
  creator?: string | null;
  character_version?: string | null;
}

export interface CharacterSummary extends CharacterBaseFields, CharacterPortraitMetadata {
  id: string;
  deleted_at?: string | null;
  updated_at?: string | null;
}

export interface CharacterDetail extends CharacterSummary {
  raw_source_json?: Record<string, unknown> | null;
  lorebook_status?: 'absent' | 'present_not_used_in_v1';
  lorebook_json?: Record<string, unknown> | null;
  source_format?: string | null;
  warnings?: string[];
}

export interface CharacterEditorPayload extends CharacterBaseFields, CharacterPortraitMetadata {}

export interface CharacterImportResult {
  character: CharacterDetail;
  warnings: string[];
  source_format: string;
}

export interface CharacterDeleteResult {
  character_id: string;
  deleted_at: string;
  preserved_thread_ids: string[];
  strategy: 'soft_delete' | 'detach_threads';
}

export interface CharacterV2Export {
  spec: string;
  spec_version: string;
  data: CharacterBaseFields & Record<string, unknown>;
  [key: string]: unknown;
}

export interface ThreadSummary {
  id: string;
  character_id: string;
  title: string | null;
  character_name?: string | null;
  character_portrait_url?: string | null;
  character_portrait_asset_id?: string | null;
  character_portrait_storage_path?: string | null;
  last_message_snippet?: string | null;
  last_message_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface ListResponse<T> {
  items: T[];
}

export interface CreateThreadRequest {
  character_id: string;
  title?: string;
  alternate_greeting_index?: number;
}

export interface CreateThreadResponse {
  thread_id: string;
}

export interface RenameThreadRequest {
  title: string;
}

export interface RenameThreadResponse {
  thread_id: string;
  title: string;
  updated_at?: string | null;
}

export interface DeleteThreadResponse {
  thread_id: string;
  deleted: boolean;
}

export interface ThreadDetail extends ThreadSummary {
  messages: ThreadMessage[];
}

export interface SettingsPayload {
  web_url: string;
  ai_backend_url: string;
  llm_base_url: string;
  llm_model: string;
  llm_api_key_configured: boolean;
  save_ai_audio: boolean;
  save_mic_audio: boolean;
  vad_threshold: number;
  vad_end_silence_ms: number;
  stt_model: string;
  tts_default_engine: string;
  ai_backend_status: AiBackendSettingsStatus;
}

export interface SettingsUpdatePayload {
  web_url?: string | null;
  ai_backend_url?: string | null;
  llm_base_url?: string | null;
  llm_model?: string | null;
  llm_api_key?: string | null;
  save_ai_audio?: boolean | null;
  save_mic_audio?: boolean | null;
  vad_threshold?: number | null;
  vad_end_silence_ms?: number | null;
  stt_model?: string | null;
  tts_default_engine?: string | null;
}

export interface EndpointTestResult {
  status: EndpointStatus;
  message?: string;
  probe?: string;
  target_base_url?: string;
}

export interface AiBackendEngineStatus {
  id?: string;
  engine_id?: string;
  label?: string | null;
  available?: boolean;
  state?: string | null;
  resident?: boolean | null;
  unavailable_reason?: string | null;
}

export interface AiBackendSettingsStatus {
  endpoint_status: EndpointStatus;
  stt_model?: string | null;
  vad_ready?: boolean;
  resident_tts_engine?: string | null;
  available_engines?: Array<string | AiBackendEngineStatus>;
  loading_engine?: string | null;
  vram_used_mb?: number | null;
  vram_headroom_mb?: number | null;
}
