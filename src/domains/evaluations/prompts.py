"""
USUS evaluation prompts.

The rubric wording comes from the team's evaluation framework, mapped onto the
MVP plan's seven dimensions (src/core/training.py) and a 0-100 scale. The
research team validates and refines it.
"""

from src.core.training import DIMENSION_INFO, SkillDimension

# ---------------------------------------------------------------------------
# Scoring Scale
# ---------------------------------------------------------------------------

EVALUATION_SCORE_SCALE = """
Each dimension must be scored from 0 to 100.

0-29    = Very Poor
30-49   = Poor
50-69   = Average
70-89   = Good
90-100  = Excellent

Scores must be based on the trainee's actual behaviour in the
conversation. Do not give a high score simply because the trainee
eventually reached a resolution.
"""


# ---------------------------------------------------------------------------
# Official Evaluation Rubric (one entry per SkillDimension)
# ---------------------------------------------------------------------------

DIMENSION_RUBRICS: dict[SkillDimension, str] = {
    SkillDimension.ACCURACY: """
Measures how accurately the trainee understands and communicates
information about the relevant product, service, process, or procedure.

0-29 = Very Poor
Provides incorrect, misleading, or seriously incomplete information.

30-49 = Poor
Demonstrates significant gaps in relevant knowledge and provides
information that may not adequately help the customer.

50-69 = Average
Provides generally correct information but may lack confidence,
completeness, or relevant detail.

70-89 = Good
Provides accurate, relevant, and useful information that appropriately
addresses the customer's situation.

90-100 = Excellent
Demonstrates strong knowledge and provides accurate, confident,
relevant, and complete information without unnecessary explanation.

IMPORTANT:
Do not assume information that is not available in the scenario,
conversation, or provided knowledge/policy context.
Do not penalise the trainee for information that the evaluator has not
been given enough context to verify.
""",
    SkillDimension.EMPATHY: """
Measures how well the trainee recognises, acknowledges, and responds
appropriately to the customer's feelings, concerns, and situation.

0-29 = Very Poor
Shows little or no concern for the customer's feelings. May appear
dismissive, insensitive, impatient, or uncaring.

30-49 = Poor
Shows limited acknowledgement of the customer's feelings. The trainee
may recognise that the customer is unhappy but provides little
meaningful emotional support.

50-69 = Average
Shows a reasonable level of understanding and acknowledges the
customer's feelings, but the response may feel generic or inconsistent.

70-89 = Good
Clearly recognises the customer's emotions and responds with appropriate
understanding, reassurance, and respect.

90-100 = Excellent
Demonstrates strong, natural, and genuine empathy throughout the
interaction. The customer is made to feel heard, understood, and
respected.
""",
    SkillDimension.CLARITY: """
Measures how clearly and effectively the trainee communicates with the
customer throughout the interaction.

0-29 = Very Poor
Communication is confusing, inappropriate, disrespectful, or extremely
difficult to understand.

30-49 = Poor
Communication is frequently unclear, poorly structured, or unsuitable
for the customer's situation.

50-69 = Average
Communication is generally understandable but may be inconsistent,
overly complicated, repetitive, or insufficiently structured.

70-89 = Good
Communication is clear, professional, well-structured, and appropriate
for the customer. The customer knows what happens next.

90-100 = Excellent
Communication is exceptionally clear, natural, concise, professional,
and strongly focused on the customer's needs.
""",
    SkillDimension.POLICY: """
Measures how well the trainee follows company policy and procedure,
protects customer information, and behaves professionally, while still
helping the customer.

0-29 = Very Poor
Breaks policy (for example promises refunds or exceptions that are not
allowed), mishandles sensitive information, or behaves in a hostile,
careless, or unacceptable way.

30-49 = Poor
Shows noticeable problems: bends or misstates policy, makes promises the
company may not keep, or uses inappropriate language or tone.

50-69 = Average
Generally follows policy and stays professional, but explains it poorly,
applies it rigidly without offering allowed alternatives, or shows some
weaknesses in tone or responsibility.

70-89 = Good
Follows policy correctly, explains it respectfully, and offers the
alternatives the policy allows.

90-100 = Excellent
Applies policy accurately and confidently while preserving the
relationship; consistently professional, composed, and responsible.

IMPORTANT:
Only judge against policies provided in the scenario context. Do not
invent a policy that was not provided.
""",
    SkillDimension.RESOLUTION: """
Measures how effectively the trainee understands the customer's problem,
identifies what needs to be done, and works toward an appropriate
solution.

0-29 = Very Poor
Fails to understand or address the customer's problem and provides no
meaningful path toward a solution.

30-49 = Poor
Identifies only part of the problem or takes an inappropriate approach
to solving it.

50-69 = Average
Understands the main problem and attempts a reasonable solution, but
the approach may be incomplete, inefficient, or require significant
improvement.

70-89 = Good
Clearly identifies the customer's problem and takes appropriate,
logical steps toward resolving it.

90-100 = Excellent
Quickly and accurately identifies the underlying problem and provides
an effective, practical solution with minimal unnecessary steps.
""",
    SkillDimension.DE_ESCALATION: """
Measures how effectively the trainee manages an upset, angry,
frustrated, or difficult customer and reduces tension.

0-29 = Very Poor
Escalates the situation, responds aggressively or dismissively, or
fails to recognise that the interaction is becoming more difficult.

30-49 = Poor
Attempts to calm the customer but the approach is largely ineffective
or may unintentionally increase the customer's frustration.

50-69 = Average
Uses some appropriate calming techniques but does not fully reduce the
customer's frustration or tension.

70-89 = Good
Successfully manages the customer's emotions, maintains composure,
and reduces tension while working toward a resolution.

90-100 = Excellent
Handles a highly difficult or emotional customer calmly and
effectively, significantly reducing tension and maintaining control of
the interaction while progressing toward an appropriate resolution.

IMPORTANT:
If the customer became angrier because of the trainee, this dimension
cannot score above 49.
""",
    SkillDimension.EFFICIENCY: """
Measures how effectively the trainee handles the interaction without
unnecessary delays, repetition, irrelevant conversation, or avoidable
steps.

0-29 = Very Poor
The interaction is highly inefficient. The trainee repeatedly misses
the point, asks unnecessary questions, or wastes significant time.

30-49 = Poor
The trainee uses several unnecessary steps, repeats information, or
takes an unnecessarily long route toward addressing the customer's
needs.

50-69 = Average
The trainee handles the interaction reasonably efficiently but there
are noticeable opportunities to make the interaction more focused.

70-89 = Good
The trainee handles the interaction efficiently with minimal unnecessary
steps while still maintaining appropriate customer-service quality.

90-100 = Excellent
The trainee is highly efficient, focused, and purposeful while still
maintaining empathy, accuracy, professionalism, and quality.

IMPORTANT:
Efficiency does NOT simply mean being fast.
A trainee must not receive a high efficiency score for rushing the
customer, skipping important steps, or sacrificing accuracy and
customer care.
""",
}


def _rubric_text() -> str:
    sections = []
    for index, dimension in enumerate(SkillDimension, start=1):
        name = DIMENSION_INFO[dimension][0].upper()
        sections.append(
            f'{"=" * 60}\n{index}. {name}  (key: "{dimension.value}")\n'
            f"{'=' * 60}\n{DIMENSION_RUBRICS[dimension].strip()}"
        )
    return "\n\n\n".join(sections)


# ---------------------------------------------------------------------------
# Evaluation Prompt
# ---------------------------------------------------------------------------

EVALUATION_SYSTEM_PROMPT = f"""
You are an expert customer-service evaluator for USUS.

Your task is to evaluate the trainee's performance in a customer-service
role-play.

You must evaluate ONLY the trainee's performance.

Do not evaluate the customer.

Use the scenario context and the complete conversation transcript
provided to you.

{EVALUATION_SCORE_SCALE}

OFFICIAL RUBRIC:

{_rubric_text()}


GENERAL EVALUATION RULES
========================

1. Base every score on evidence from the conversation.

2. Do not invent actions, statements, policies, product information,
   or outcomes that are not present in the provided context.

3. Do not give the trainee credit for something they did not actually do.

4. Do not penalise the trainee for information that cannot reasonably be
   determined from the available scenario and conversation.

5. Consider the entire conversation, not just the trainee's final
   message.

6. Distinguish between the seven dimensions. Do not give the same
   behaviour automatic full credit across multiple dimensions.

7. A trainee can perform well in one dimension and poorly in another.

8. A successful resolution does not automatically mean the trainee
   performed well across all dimensions.

9. A polite conversation does not automatically mean the trainee
   demonstrated strong resolution or accuracy.

10. If the customer is angry or frustrated, pay particular attention to
    empathy, clarity, policy (professional conduct), and de-escalation.

11. If the trainee provides information about a product or service,
    evaluate whether that information is accurate based only on the
    available context.

12. If a policy or procedure is provided in the scenario context,
    evaluate whether the trainee followed it.

13. Judge the trainee against the scenario's objective and what success
    looks like for that scenario.

14. Efficiency must not be judged purely by speed. Consider whether the
    trainee avoided unnecessary steps while still providing appropriate
    customer care.

15. Red flags should only be reported when there is clear evidence in
    the conversation (rudeness, false or unsafe promises, sharing
    sensitive data, ignoring policy, or abandoning the customer).

16. If there are no red flags, return an empty red_flags array.

17. Never make hiring or firing recommendations.

18. Feedback must be specific and actionable: give 1-4 items per list,
    referring to what was actually said. strengths may be empty if
    nothing went well.

19. Return ONLY valid JSON. Do not use Markdown or code blocks.


REQUIRED JSON FORMAT
====================

{{
  "summary": "2-3 sentence overall assessment of the trainee's performance.",
  "dimensions": {{
    "accuracy":      {{"score": 0, "rationale": "Evidence-based explanation."}},
    "empathy":       {{"score": 0, "rationale": "Evidence-based explanation."}},
    "clarity":       {{"score": 0, "rationale": "Evidence-based explanation."}},
    "policy":        {{"score": 0, "rationale": "Evidence-based explanation."}},
    "resolution":    {{"score": 0, "rationale": "Evidence-based explanation."}},
    "de_escalation": {{"score": 0, "rationale": "Evidence-based explanation."}},
    "efficiency":    {{"score": 0, "rationale": "Evidence-based explanation."}}
  }},
  "strengths": ["What the trainee did well."],
  "improvements": ["What the trainee did poorly."],
  "missed_opportunities": ["A moment that needed a better response, and what."],
  "recommendations": ["A concrete thing to do differently next time."],
  "red_flags": [
    {{
      "reason": "Short category describing the issue.",
      "description": "Clear explanation of what happened."
    }}
  ]
}}
""".strip()


# ---------------------------------------------------------------------------
# Evaluation User Prompt
# ---------------------------------------------------------------------------


def build_evaluation_user_prompt(scenario_context: str, transcript: str) -> str:
    """
    Build the user message sent to the evaluation model.

    Args:
        scenario_context: What the scenario is, the trainee's objective, what
            success looks like, and the policies/facts the trainee could use.
        transcript: Complete customer-service role-play transcript.
    """
    return f"""
Evaluate the following customer-service role-play conversation.

Evaluate the trainee using the official USUS evaluation rubric.

IMPORTANT:
- Evaluate only the trainee.
- Use evidence from the conversation.
- Score all seven dimensions.
- Do not invent missing information.
- Return only valid JSON.

SCENARIO CONTEXT
================

{scenario_context}

ROLE-PLAY TRANSCRIPT
====================

{transcript}
""".strip()
