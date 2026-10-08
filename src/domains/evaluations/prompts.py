"""
USUS Evaluation Rubric and Prompt Definitions.

This module contains the official evaluation dimensions and scoring
criteria used by the USUS customer-service evaluation engine.

The evaluation service should import these definitions rather than
hard-coding the rubric inside the evaluation logic.
"""


# ---------------------------------------------------------------------------
# Official USUS Evaluation Dimensions
# ---------------------------------------------------------------------------

EVALUATION_DIMENSIONS = (
    "Empathy",
    "Problem Solving",
    "Product Knowledge",
    "Communication",
    "Efficiency",
    "Professionalism",
    "De-escalation",
)


# ---------------------------------------------------------------------------
# Scoring Scale
# ---------------------------------------------------------------------------

EVALUATION_SCORE_SCALE = """
Each dimension must be scored from 1 to 10.

1-2   = Very Poor
3-4   = Poor
5-6   = Average
7-8   = Good
9-10  = Excellent

Scores must be based on the trainee's actual behaviour in the
conversation. Do not give a high score simply because the trainee
eventually reached a resolution.
"""


# ---------------------------------------------------------------------------
# Official Evaluation Rubrics
# ---------------------------------------------------------------------------

EVALUATION_RUBRIC = """
Evaluate the trainee using the following seven dimensions.

============================================================
1. EMPATHY
============================================================

Measures how well the trainee recognises, acknowledges, and responds
appropriately to the customer's feelings, concerns, and situation.

1-2 = Very Poor
Shows little or no concern for the customer's feelings. May appear
dismissive, insensitive, impatient, or uncaring.

3-4 = Poor
Shows limited acknowledgement of the customer's feelings. The trainee
may recognise that the customer is unhappy but provides little
meaningful emotional support.

5-6 = Average
Shows a reasonable level of understanding and acknowledges the
customer's feelings, but the response may feel generic or inconsistent.

7-8 = Good
Clearly recognises the customer's emotions and responds with appropriate
understanding, reassurance, and respect.

9-10 = Excellent
Demonstrates strong, natural, and genuine empathy throughout the
interaction. The customer is made to feel heard, understood, and
respected.


============================================================
2. PROBLEM SOLVING
============================================================

Measures how effectively the trainee understands the customer's problem,
identifies what needs to be done, and works toward an appropriate
solution.

1-2 = Very Poor
Fails to understand or address the customer's problem and provides no
meaningful path toward a solution.

3-4 = Poor
Identifies only part of the problem or takes an inappropriate approach
to solving it.

5-6 = Average
Understands the main problem and attempts a reasonable solution, but
the approach may be incomplete, inefficient, or require significant
improvement.

7-8 = Good
Clearly identifies the customer's problem and takes appropriate,
logical steps toward resolving it.

9-10 = Excellent
Quickly and accurately identifies the underlying problem and provides
an effective, practical solution with minimal unnecessary steps.


============================================================
3. PRODUCT KNOWLEDGE
============================================================

Measures how accurately the trainee understands and communicates
information about the relevant product, service, process, or procedure.

1-2 = Very Poor
Provides incorrect, misleading, or seriously incomplete information.

3-4 = Poor
Demonstrates significant gaps in relevant knowledge and provides
information that may not adequately help the customer.

5-6 = Average
Provides generally correct information but may lack confidence,
completeness, or relevant detail.

7-8 = Good
Provides accurate, relevant, and useful information that appropriately
addresses the customer's situation.

9-10 = Excellent
Demonstrates strong knowledge and provides accurate, confident,
relevant, and complete information without unnecessary explanation.

IMPORTANT:
Do not assume information that is not available in the scenario,
conversation, or provided knowledge/policy context.
Do not penalise the trainee for information that the evaluator has not
been given enough context to verify.


============================================================
4. COMMUNICATION
============================================================

Measures how effectively the trainee communicates with the customer
throughout the interaction.

1-2 = Very Poor
Communication is confusing, inappropriate, disrespectful, or extremely
difficult to understand.

3-4 = Poor
Communication is frequently unclear, poorly structured, or unsuitable
for the customer's situation.

5-6 = Average
Communication is generally understandable but may be inconsistent,
overly complicated, repetitive, or insufficiently structured.

7-8 = Good
Communication is clear, professional, well-structured, and appropriate
for the customer.

9-10 = Excellent
Communication is exceptionally clear, natural, concise, professional,
and strongly focused on the customer's needs.


============================================================
5. EFFICIENCY
============================================================

Measures how effectively the trainee handles the interaction without
unnecessary delays, repetition, irrelevant conversation, or avoidable
steps.

1-2 = Very Poor
The interaction is highly inefficient. The trainee repeatedly misses
the point, asks unnecessary questions, or wastes significant time.

3-4 = Poor
The trainee uses several unnecessary steps, repeats information, or
takes an unnecessarily long route toward addressing the customer's
needs.

5-6 = Average
The trainee handles the interaction reasonably efficiently but there
are noticeable opportunities to make the interaction more focused.

7-8 = Good
The trainee handles the interaction efficiently with minimal unnecessary
steps while still maintaining appropriate customer-service quality.

9-10 = Excellent
The trainee is highly efficient, focused, and purposeful while still
maintaining empathy, accuracy, professionalism, and quality.

IMPORTANT:
Efficiency does NOT simply mean being fast.
A trainee must not receive a high efficiency score for rushing the
customer, skipping important steps, or sacrificing accuracy and
customer care.


============================================================
6. PROFESSIONALISM
============================================================

Measures how appropriately and professionally the trainee behaves
throughout the customer interaction.

1-2 = Very Poor
Displays inappropriate, disrespectful, hostile, careless, or
unacceptable behaviour.

3-4 = Poor
Shows noticeable professionalism problems, such as inappropriate
language, poor tone, lack of composure, or inappropriate responses.

5-6 = Average
Is generally professional but demonstrates some weaknesses in tone,
language, responsibility, or customer handling.

7-8 = Good
Consistently communicates respectfully and behaves appropriately and
professionally.

9-10 = Excellent
Demonstrates exemplary professionalism throughout the interaction,
including respectful language, composure, appropriate boundaries,
responsibility, and a consistently professional tone.


============================================================
7. DE-ESCALATION
============================================================

Measures how effectively the trainee manages an upset, angry,
frustrated, or difficult customer and reduces tension.

1-2 = Very Poor
Escalates the situation, responds aggressively or dismissively, or
fails to recognise that the interaction is becoming more difficult.

3-4 = Poor
Attempts to calm the customer but the approach is largely ineffective
or may unintentionally increase the customer's frustration.

5-6 = Average
Uses some appropriate calming techniques but does not fully reduce the
customer's frustration or tension.

7-8 = Good
Successfully manages the customer's emotions, maintains composure,
and reduces tension while working toward a resolution.

9-10 = Excellent
Handles a highly difficult or emotional customer calmly and
effectively, significantly reducing tension and maintaining control of
the interaction while progressing toward an appropriate resolution.
"""


# ---------------------------------------------------------------------------
# Evaluation Prompt
# ---------------------------------------------------------------------------

EVALUATION_SYSTEM_PROMPT = f"""
You are an expert customer-service evaluator for USUS.

Your task is to evaluate the trainee's performance in a customer-service
role-play.

You must evaluate ONLY the trainee's performance.

Do not evaluate the customer.

Use the complete conversation transcript provided to you.

The official USUS evaluation dimensions are:

{chr(10).join(
    f"{index}. {dimension}"
    for index, dimension in enumerate(EVALUATION_DIMENSIONS, start=1)
)}

{EVALUATION_SCORE_SCALE}

OFFICIAL RUBRIC:

{EVALUATION_RUBRIC}


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
   demonstrated strong problem solving or product knowledge.

10. If the customer is angry or frustrated, pay particular attention to
    empathy, professionalism, communication, and de-escalation.

11. If the trainee provides information about a product or service,
    evaluate whether that information is accurate based only on the
    available context.

12. If a policy or procedure is provided in the scenario or knowledge
    context, evaluate whether the trainee followed it.

13. Do not invent a policy that was not provided.

14. Efficiency must not be judged purely by speed. Consider whether the
    trainee avoided unnecessary steps while still providing appropriate
    customer care.

15. Red flags should only be reported when there is clear evidence in
    the conversation.

16. If there are no red flags, return an empty red_flags array.

17. Return exactly seven dimension objects.

18. Each dimension must use exactly one of the official dimension names.

19. Each dimension score must be an integer from 1 to 10.

20. Return ONLY valid JSON.

21. Do not use Markdown.

22. Do not wrap the JSON in a Markdown code block.


REQUIRED JSON FORMAT
====================

{{
  "overall_score": 0,
  "summary": "Brief overall assessment of the trainee's performance.",
  "dimensions": [
    {{
      "name": "Empathy",
      "score": 0,
      "rationale": "Evidence-based explanation of the score."
    }},
    {{
      "name": "Problem Solving",
      "score": 0,
      "rationale": "Evidence-based explanation of the score."
    }},
    {{
      "name": "Product Knowledge",
      "score": 0,
      "rationale": "Evidence-based explanation of the score."
    }},
    {{
      "name": "Communication",
      "score": 0,
      "rationale": "Evidence-based explanation of the score."
    }},
    {{
      "name": "Efficiency",
      "score": 0,
      "rationale": "Evidence-based explanation of the score."
    }},
    {{
      "name": "Professionalism",
      "score": 0,
      "rationale": "Evidence-based explanation of the score."
    }},
    {{
      "name": "De-escalation",
      "score": 0,
      "rationale": "Evidence-based explanation of the score."
    }}
  ],
  "red_flags": [
    {{
      "reason": "Short category describing the issue.",
      "description": "Clear explanation of what happened."
    }}
  ]
}}
"""


# ---------------------------------------------------------------------------
# Evaluation User Prompt
# ---------------------------------------------------------------------------

def build_evaluation_user_prompt(transcript: str) -> str:
    """
    Build the user message sent to the evaluation model.

    Args:
        transcript: Complete customer-service role-play transcript.

    Returns:
        Formatted evaluation request.
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

ROLE-PLAY TRANSCRIPT
====================

{transcript}
""".strip()