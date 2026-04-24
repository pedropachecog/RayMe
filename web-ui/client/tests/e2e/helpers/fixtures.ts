import type {
  CharacterDetail,
  MessageAlternateSourceAction,
  ThreadDetail,
  ThreadMessage
} from '../../../src/lib/api/types';

export const PHASE1_LOCAL_LLM_URL = 'http://192.168.1.190:8001/v1';
export const PHASE1_LOCAL_LLM_MODEL = 'unsloth/Qwen3.5-27B';

export function makeCharacter(overrides: Partial<CharacterDetail> = {}): CharacterDetail {
  return {
    id: 'phase011-character',
    name: 'Phase 01.1 Aster',
    description: 'A deterministic Phase 01.1 character fixture.',
    personality: 'Careful, warm, and concise.',
    scenario: 'A test relay room used for browser acceptance.',
    first_mes: 'Default Phase 01.1 greeting.',
    mes_example: '<START>\n{{char}}: A stable example line.',
    system_prompt: 'Stay consistent with the fixture contract.',
    creator_notes: 'Phase 01.1 creator notes.',
    character_notes: 'Phase 01.1 character notes.',
    tags: ['phase-01.1', 'fixture'],
    alternate_greetings: ['Alternate greeting zero.', 'Alternate greeting selected.'],
    post_history_instructions: 'Preserve selected branch continuity.',
    creator: 'RayMe',
    character_version: '1.0',
    raw_source_json: {
      spec: 'chara_card_v3',
      spec_version: '3.0',
      data: {
        name: 'Phase 01.1 Aster',
        first_mes: 'Default Phase 01.1 greeting.'
      }
    },
    lorebook_status: 'present_not_used_in_v1',
    lorebook_json: {
      entries: [{ keys: ['phase'], content: 'Stored for later versions.' }]
    },
    source_format: 'v3_json',
    warnings: ['Lorebook present - not used in v1'],
    deleted_at: null,
    updated_at: null,
    portrait_url: '/api/characters/phase011-character/portrait?asset_id=phase011-portrait',
    portrait_path: null,
    portrait_asset_id: 'phase011-portrait',
    portrait_storage_path: 'characters/phase011-character/phase011-portrait.png',
    portrait_mime_type: 'image/png',
    portrait_size_bytes: 68,
    portrait_updated_at: null,
    ...overrides
  };
}

export function makeAiMessage(
  id = 'phase011-ai-message',
  threadId = 'phase011-thread',
  sequence = 0,
  content = 'Default Phase 01.1 AI message.',
  sourceAction: MessageAlternateSourceAction = 'first_mes',
  alternateIndex = 0
): ThreadMessage {
  const alternateId = `alt-${id}-${sourceAction}-${alternateIndex}`;
  return {
    id,
    thread_id: threadId,
    message_kind: 'ai_text',
    role: 'assistant',
    sequence,
    content_text: content,
    selected_alternate_id: alternateId,
    alternates: [
      {
        id: alternateId,
        message_id: id,
        alternate_index: alternateIndex,
        content_text: content,
        source_action: sourceAction,
        created_at: null
      }
    ],
    stale_after_edit: false,
    created_at: null,
    updated_at: null
  };
}

export function makeUserMessage(
  id = 'phase011-user-message',
  threadId = 'phase011-thread',
  sequence = 1,
  content = 'Default Phase 01.1 user message.'
): ThreadMessage {
  return {
    id,
    thread_id: threadId,
    message_kind: 'user_text',
    role: 'user',
    sequence,
    content_text: content,
    selected_alternate_id: null,
    alternates: [],
    stale_after_edit: false,
    created_at: null,
    updated_at: null
  };
}

export function makeThreadDetail(overrides: Partial<ThreadDetail> = {}): ThreadDetail {
  const character = makeCharacter();
  const threadId = overrides.id ?? 'phase011-thread';
  const defaultMessages = [
    makeAiMessage('phase011-opening-message', threadId, 0, character.first_mes ?? '', 'first_mes')
  ];
  const messages = [...(overrides.messages ?? defaultMessages)].sort((left, right) => {
    return left.sequence - right.sequence;
  });
  const lastMessage = messages.at(-1);

  return {
    id: threadId,
    character_id: character.id,
    title: character.name,
    character_name: character.name,
    character_portrait_url: character.portrait_url,
    character_portrait_asset_id: character.portrait_asset_id,
    character_portrait_storage_path: character.portrait_storage_path,
    last_message_snippet: lastMessage?.content_text ?? null,
    last_message_at: null,
    created_at: null,
    updated_at: null,
    messages,
    ...overrides,
    messages
  };
}
