"""
Remaining private symbol violations in unit tests.
These need to be fixed to comply with the rule: tests must only access public symbols.
See conversation context for the approach to each fix.
"""

# --- test_narrator_agent.py ---
# Line 175-176: narrator._scene_instructions accessed directly
#   Fix: test through adapter capture — construct narrator with custom personality,
#        call narrate() with scene_opening frame, assert personality appears in
#        the system message passed to the adapter.
#
# Lines 468, 475, 480, 486, 492, 498: narrator._adapter accessed directly
#   Fix: use the mock_adapter reference returned by _make_narrator() instead of
#        going through narrator._adapter — they are the same object.
#
# Lines 524, 542, 666: narrator._plan_agent = Agent(...) post-construction mutation
#   Fix: construct NarratorAgent with plan_agent=<the agent> in the constructor
#        rather than mutating the private attribute after construction.

# --- test_pydantic_ai_adapter.py ---
# Line 116: adapter.model.profile is adapter_module._ollama_structured_output_profile
#   Fix: assert adapter.model.profile.default_structured_output_mode == "prompted"
#        (tests behavior, not object identity with a private symbol)
#
# Line 126: _ollama_structured_output_profile("...") called directly
#   Fix: test through PydanticAIAdapter.from_env() — assert the constructed
#        adapter's model profile uses prompted mode.

# --- test_game_orchestrator.py ---
# Lines 43, 44, 50, 51, 57, 58: orch._character_creation_orchestrator,
#   orch._campaign_creation_orchestrator, orch._startup_orchestrator accessed
#   Fix: keep reference to the mock injected at construction time and assert on
#        that mock directly instead of going through orch._attribute.

# --- test_startup_orchestrator.py ---
# Lines 52, 58, 64, 65, 71, 72, 78, 84: orch._module_orchestrator,
#   orch._campaign_creation_orchestrator accessed
#   Fix: same pattern — assert on the injected mock directly.

# --- test_campaign_creation_orchestrator.py ---
# Line 111: orch._io.display.call_args_list accessed
#   Fix: inject a mock IO at construction, assert on the mock's display calls directly.
#
# Line 133: orch._module_orchestrator.run.assert_called_once()
#   Fix: assert on the injected mock module_orchestrator directly.

# --- test_module_orchestrator.py ---
# Line 178: orch._repos.module accessed
#   Fix: verify through observable behavior (module repo methods called) rather
#        than inspecting internal state.
#
# Lines 217, 373: orch._io.display.call_args_list / assert_any_call
#   Fix: inject mock IO, assert on it directly.
#
# Line 322: orch._agents.module_generator.generate.return_value set
#   Fix: inject mock agents at construction, configure the mock before passing it in.
#
# Line 460: orchestrator._create_and_run_encounter(...) called directly
#   Fix: test through the public run() method with state that triggers
#        _create_and_run_encounter to be called.
