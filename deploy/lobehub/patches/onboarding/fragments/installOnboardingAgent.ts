// LCA onboarding agent creation (ADR-0252 D7).
// POST /lca-api/v1/assistants with client_id/name/from_role/initial_skills.

export interface InstallOnboardingAgentArgs {
  clientId: string;
  name: string;
  fromRole: string;
  initialSkills: string[];
}

export interface InstallOnboardingAgentResult {
  assistantId: string;
  agentId?: string | null;
  homePath?: string;
  revisionSeq?: number;
}

export const installOnboardingAgent = async (
  args: InstallOnboardingAgentArgs,
): Promise<InstallOnboardingAgentResult> => {
  const response = await fetch('/lca-api/v1/assistants', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      client_id: args.clientId,
      name: args.name,
      from_role: args.fromRole,
      initial_skills: args.initialSkills,
    }),
  });
  if (!response.ok) {
    let detail = '';
    try {
      const body = await response.json();
      detail = body?.error?.detail || body?.error?.code || '';
    } catch {
      // ignore parse errors
    }
    throw new Error(`create assistant failed: ${response.status} ${detail}`);
  }
  const data = await response.json();
  return {
    assistantId: data.assistant_id,
    agentId: data.agent_id ?? null,
    homePath: data.home_path,
    revisionSeq: data.revision_seq,
  };
};