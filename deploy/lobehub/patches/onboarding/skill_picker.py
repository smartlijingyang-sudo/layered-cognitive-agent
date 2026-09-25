"""Patch: skill_picker — LCA onboarding agent creation with skill checkboxes.

ADR-0252 D7：``AgentPickerStep`` 从 LCA presets 选角色 + 勾选技能（默认全选），
Continue 调 LCA ``POST /v1/assistants``（``client_id``/``name``/``from_role``/
``initial_skills``）再 ``finishOnboarding()``。
"""

from __future__ import annotations

from pathlib import Path

from deploy.lobehub.engine import PatchContext, PatchMeta

_FRAGMENT_DIR = Path(__file__).parent / "fragments"

meta = PatchMeta(
    name="skill_picker",
    description="LCA onboarding: role picker + skill checkboxes + agent creation",
    files=(
        "src/services/installOnboardingAgent.ts",
        "src/routes/onboarding/features/AgentPickerStep/index.tsx",
    ),
    risk="high",
    category="onboarding",
    depends_on=("lca_presets",),
    why="ADR-0252 D7: onboarding creates an isolated LCA assistant with selected skills",
    technical_detail=(
        "Adds installOnboardingAgent service; patches AgentPickerStep to load "
        "skill capabilities, default all checked, and create the assistant via "
        "POST /lca-api/v1/assistants."
    ),
    verify_file="src/routes/onboarding/features/AgentPickerStep/index.tsx",
    verify_marker="LCA skill_picker",
)


def apply(ctx: PatchContext) -> bool:
    service_rel = "src/services/installOnboardingAgent.ts"
    step_rel = "src/routes/onboarding/features/AgentPickerStep/index.tsx"

    if ctx.has_marker(step_rel, "LCA skill_picker"):
        return False

    # 1) New service file.
    service_source = (_FRAGMENT_DIR / "installOnboardingAgent.ts").read_text(encoding="utf-8")
    ctx.write(service_rel, service_source)

    # 2) Patch AgentPickerStep.
    text = ctx.read(step_rel)

    # 2a. Checkbox import.
    anchor_import = "import { Button } from '@lobehub/ui/base-ui';"
    repl_import = "import { Button, Checkbox } from '@lobehub/ui/base-ui';"
    if anchor_import not in text:
        raise AssertionError("skill_picker: base-ui import anchor not found")
    text = text.replace(anchor_import, repl_import, 1)

    # 2b. Service imports.
    anchor_services = "import { installMarketplaceAgents } from '@/services/installMarketplaceAgents';"
    repl_services = (
        "import { fetchOnboardingSkillCapabilities } from '@/services/agentMarketplace';\n"
        "import { installOnboardingAgent } from '@/services/installOnboardingAgent';"
    )
    if anchor_services not in text:
        raise AssertionError("skill_picker: services import anchor not found")
    text = text.replace(anchor_services, repl_services, 1)

    # 2c. Skill state.
    anchor_state = "  const [selected, setSelected] = useState<Set<string>>(() => new Set());"
    repl_state = anchor_state + """
  const [skills, setSkills] = useState<
    Array<{ id: string; name: string; description: string }>
  >([]);
  const [checkedSkills, setCheckedSkills] = useState<Set<string>>(() => new Set());"""
    if anchor_state not in text:
        raise AssertionError("skill_picker: state anchor not found")
    text = text.replace(anchor_state, repl_state, 1)

    # 2d. Load skills + default all checked.
    anchor_memo = """  const [active, setActive] = useState<ActiveCategory>('all');
  const visibleTemplates = useMemo(
    () =>
      active === 'all'
        ? orderedTemplates
        : orderedTemplates.filter((tpl) => tpl.category === active),
    [active, orderedTemplates],
  );"""
    repl_memo = anchor_memo + """

  // LCA skill_picker: load skill capabilities, default all checked (ADR-0252 D7).
  useEffect(() => {
    fetchOnboardingSkillCapabilities()
      .then((items) => {
        setSkills(items);
        setCheckedSkills(new Set(items.map((s) => s.id)));
      })
      .catch((error) => console.error('[AgentPickerStep] skills load failed', error));
  }, []);"""
    if anchor_memo not in text:
        raise AssertionError("skill_picker: visibleTemplates memo anchor not found")
    text = text.replace(anchor_memo, repl_memo, 1)

    # 2e. handleContinue -> installOnboardingAgent.
    anchor_continue = """    const selectedTemplateIds = [...selected];
    trackOnboardingMarketplacePicked({ categoryHints, requestId, selectedTemplateIds });
    try {
      await installMarketplaceAgents(selectedTemplateIds);
    } catch (installError) {
      console.error('[AgentPickerStep] install failed', installError);
    }
    await finish('continue', selectedTemplateIds.length);
  }, [categoryHints, finish, requestId, selected]);"""
    repl_continue = """    const selectedTemplateIds = [...selected];
    trackOnboardingMarketplacePicked({ categoryHints, requestId, selectedTemplateIds });
    const firstRole = allTemplates.find((tpl) => tpl.id === selectedTemplateIds[0]);
    try {
      await installOnboardingAgent({
        clientId: requestId,
        name: firstRole?.title || 'My Agent',
        fromRole: firstRole?.id || '',
        initialSkills: [...checkedSkills],
      });
    } catch (installError) {
      console.error('[AgentPickerStep] LCA install failed', installError);
    }
    await finish('continue', selectedTemplateIds.length);
  }, [allTemplates, categoryHints, checkedSkills, finish, requestId, selected]);"""
    if anchor_continue not in text:
        raise AssertionError("skill_picker: handleContinue anchor not found")
    text = text.replace(anchor_continue, repl_continue, 1)

    # 2f. Skill checkbox UI before the footer.
    anchor_footer = """      <div className={styles.footer}>"""
    repl_footer = """      {skills.length > 0 && (
        <Flexbox gap={8}>
          <Text fontSize={14} type={'secondary'}>
            Agent Skills
          </Text>
          <Flexbox gap={8} horizontal wrap>
            {skills.map((skill) => (
              <Checkbox
                key={skill.id}
                checked={checkedSkills.has(skill.id)}
                onChange={(checked) => {
                  setCheckedSkills((prev) => {
                    const next = new Set(prev);
                    if (checked) next.add(skill.id);
                    else next.delete(skill.id);
                    return next;
                  });
                }}
              >
                {skill.name}
              </Checkbox>
            ))}
          </Flexbox>
        </Flexbox>
      )}

      <div className={styles.footer}>"""
    if anchor_footer not in text:
        raise AssertionError("skill_picker: footer anchor not found")
    text = text.replace(anchor_footer, repl_footer, 1)

    ctx.write(step_rel, text)
    return True