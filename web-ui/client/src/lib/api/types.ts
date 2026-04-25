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

export type CharacterDefaultVoiceState = 'none' | 'assigned' | 'unavailable';

export interface CharacterDefaultVoice {
  id?: string | null;
  voice_id?: string | null;
  name?: string | null;
  deleted_name?: string | null;
  default_engine?: TtsEngineId | null;
  status?: 'available' | 'deleted' | string;
}

export interface CharacterDefaultVoiceFields {
  default_voice_id?: string | null;
  default_voice_state?: CharacterDefaultVoiceState;
  default_voice_label?: string | null;
  default_voice?: CharacterDefaultVoice | null;
}

export interface CharacterSummary
  extends CharacterBaseFields,
    CharacterPortraitMetadata,
    CharacterDefaultVoiceFields {
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

export interface CharacterEditorPayload
  extends CharacterBaseFields,
    CharacterPortraitMetadata,
    Pick<CharacterDefaultVoiceFields, 'default_voice_id'> {}

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

export type TtsEngineId =
  | 'f5'
  | 'xtts_v2'
  | 'qwen3_0_6b'
  | 'luxtts'
  | 'chatterbox_turbo'
  | 'tada_1b'
  | (string & {});

export interface TtsEngineAvailability {
  state?: 'idle' | 'loading' | 'resident' | 'unavailable' | string;
  available?: boolean;
  unavailable_reason?: string | null;
  resident?: boolean | null;
}

export interface TtsEngineMetadata {
  id: TtsEngineId;
  label: string;
  is_default?: boolean;
  code_license?: string | null;
  model_license?: string | null;
  caveat_chips?: string[];
  caveats?: string[];
  runtime_evidence?: string | null;
  requires_transcript?: boolean;
  supports_streaming?: boolean;
  quality_notes?: string | null;
  availability?: TtsEngineAvailability;
}

export interface VoiceAsset {
  asset_id: string;
  voice_id?: string | null;
  asset_kind?: string | null;
  storage_path?: string | null;
  content_type?: string | null;
  byte_size?: number | null;
  sha256?: string | null;
  duration_seconds?: number | null;
  sample_rate_hz?: number | null;
  channel_count?: number | null;
  warnings?: string[];
}

export interface VoiceSummary {
  voice_id: string;
  id?: string;
  asset_id?: string | null;
  name: string;
  default_engine: TtsEngineId;
  reference_transcript?: string | null;
  metadata?: Record<string, unknown>;
  status?: 'available' | 'deleted' | string;
  unavailable_label?: string | null;
  deleted_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface VoiceDetail extends VoiceSummary {}

export interface VoiceSavePayload {
  asset_id: string;
  name: string;
  default_engine: TtsEngineId;
  reference_transcript?: string | null;
  metadata?: Record<string, unknown>;
}

export interface VoicePreviewPayload {
  asset_id: string;
  name?: string | null;
  default_engine?: TtsEngineId | null;
  reference_transcript?: string | null;
  preview_text?: string | null;
  use_default_engine?: boolean;
  engine?: TtsEngineId | null;
  speech_speed?: number;
}

export interface VoiceTestPlayPayload {
  text: string;
  use_default_engine?: boolean;
  engine?: TtsEngineId | null;
  speech_speed?: number;
}

export interface VoiceSynthesisResult {
  voice_id?: string | null;
  engine?: TtsEngineId | null;
  engine_id?: TtsEngineId | null;
  status?: string | null;
  preview_id?: string | null;
  preview_url?: string | null;
  audio_url?: string | null;
  audio_base64?: string | null;
  content_type?: string | null;
  duration_ms?: number | null;
  error?: unknown;
  payload_state?: Record<string, unknown>;
}

export interface VoiceDeleteResult {
  voice_id: string;
  deleted?: boolean;
  deleted_at?: string | null;
  strategy?: 'soft_delete' | string;
  referents?: Array<Record<string, string>>;
  affected_characters?: Array<Record<string, string>>;
  tombstone?: { name?: string | null };
}
