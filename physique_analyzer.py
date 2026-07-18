"""
Solo Leveling Fitness - AI Physique Analyzer (Google Gemini version)
Analyzes a named character/person OR an uploaded photo and generates a
gamified Quest Log (Dailies, Main Story Quests, Side Quests, Level Up
Milestones) using Google's Gemini API.

Gemini was chosen here because, as of mid-2026, it consistently leads
pure vision-understanding benchmarks (MMMU Pro) among frontier models,
while being notably cheaper and faster than comparable alternatives for
image analysis tasks like this one.

Requires a Gemini API key set as the GEMINI_API_KEY environment
variable. Get one free at: https://aistudio.google.com/apikey

Uses the current "google-genai" SDK (NOT the older, deprecated
"google-generativeai" package).
"""

import os
import mimetypes
from typing import Optional, Dict

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None
    types = None


# Model choice: gemini-2.5-pro is the current stable, GA (non-preview)
# reasoning + vision model as of mid-2026. If you want to try the newer
# Gemini 3 family for stronger vision benchmarks, swap this for
# "gemini-3-pro-preview" -- just be aware preview models can change or
# be deprecated with as little as 2 weeks' notice.
MODEL_NAME = "gemini-flash-latest"


# The exact Game Master prompt template, parameterized by target.
MASTER_PROMPT_TEMPLATE = """Act as a Master Fitness RPG Game Master. I want to achieve the physique of {target}.

First, analyze their physique. Break down their dominant muscle groups, estimated body fat percentage style (lean, bulky, athletic), and the type of training required to look like them.

Second, generate a gamified 'Quest Log' for me to achieve this build. Break this down into:
- Daily Dailies (Habits): Nutrition and lifestyle tasks.
- Main Story Quests (Workout Plan): A weekly training split designed specifically for this physique.
- Side Quests (Optional Challenges): Fun, thematic fitness challenges related to the character/person.
- Level Up Milestones: How I will know I am making progress.

Please ensure the plan is realistic, safe, and progressively overloads over time. Format your response in clean Markdown with clear headers ("## Physique Breakdown", "## Daily Dailies", "## Main Story Quests", "## Side Quests", "## Level Up Milestones") so it can be rendered directly in a fitness app. Keep training advice safe, evidence-based, and appropriate for a general audience (no extreme calorie restriction, no PED references, no unsafe training advice)."""


class PhysiqueAnalyzer:
    """Generates physique-goal based Quest Logs via Google Gemini"""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get('GEMINI_API_KEY') or os.environ.get('GOOGLE_API_KEY')
        self.client = None
        if genai and self.api_key:
            self.client = genai.Client(api_key=self.api_key)

    def is_configured(self) -> bool:
        """Check whether the API key / SDK is available"""
        return self.client is not None

    def _build_contents(self, target_name: Optional[str],
                         image_path: Optional[str]) -> list:
        """Build the multimodal contents list: optional image + text prompt"""
        if target_name:
            target_desc = target_name
        else:
            target_desc = "the person shown in the attached image"

        prompt_text = MASTER_PROMPT_TEMPLATE.format(target=target_desc)

        contents = []

        if image_path and os.path.exists(image_path):
            mime_type, _ = mimetypes.guess_type(image_path)
            if not mime_type or not mime_type.startswith('image/'):
                mime_type = 'image/jpeg'

            with open(image_path, 'rb') as f:
                image_bytes = f.read()

            contents.append(types.Part.from_bytes(data=image_bytes, mime_type=mime_type))

        contents.append(prompt_text)
        return contents

    def generate_quest_log(self, target_name: Optional[str] = None,
                          image_path: Optional[str] = None) -> Dict:
        """
        Generate a Quest Log by analyzing a named character/person or an
        uploaded photo. Exactly one of target_name / image_path should be
        provided (an image takes priority if both are given).
        """
        if not target_name and not image_path:
            return {
                'success': False,
                'error': 'Provide either a character/person name or upload a photo.'
            }

        if not self.is_configured():
            return {
                'success': False,
                'error': (
                    'AI analysis is not configured. Set the GEMINI_API_KEY '
                    'environment variable and install the "google-genai" package '
                    '(pip install google-genai) to enable this feature.'
                ),
                'setup_required': True
            }

        try:
            contents = self._build_contents(target_name, image_path)

            response = self.client.models.generate_content(
                model=MODEL_NAME,
                contents=contents
            )

            quest_log_markdown = response.text

            return {
                'success': True,
                'target_name': target_name or 'Uploaded Photo Subject',
                'source_type': 'image' if image_path else 'text',
                'quest_log_markdown': quest_log_markdown
            }

        except Exception as e:
            return {
                'success': False,
                'error': f'AI generation failed: {str(e)}'
            }

    def extract_structured_weekly_plan(self, quest_log_markdown: str) -> Dict:
        """
        Take the freeform Quest Log markdown and ask Gemini to convert the
        "Main Story Quests" weekly training split specifically into strict
        structured JSON, so the daily quest system can actually run it day
        by day instead of the plan just sitting there as text.
        """
        if not self.is_configured():
            return {'success': False, 'error': 'AI analysis is not configured.'}

        main_quests_section = extract_section(quest_log_markdown, 'Main Story Quests')
        if not main_quests_section:
            main_quests_section = quest_log_markdown  # fall back to full text

        structuring_prompt = f"""Convert the following weekly workout split into STRICT JSON only -- no markdown fences, no commentary, no explanation, just the raw JSON object.

Weekly split to convert:
---
{main_quests_section}
---

Return JSON matching EXACTLY this schema (all 7 days, Monday through Sunday, day_of_week 0=Monday through 6=Sunday):

{{
  "days": [
    {{
      "day_of_week": 0,
      "day_label": "Monday",
      "focus": "short label like 'Push - Chest, Shoulders, Triceps' or 'Rest Day'",
      "is_rest": false,
      "exercises": [
        {{
          "name": "Exercise Name",
          "sets": 4,
          "reps": "8-10",
          "rest_seconds": 90,
          "notes": "brief form or intensity cue"
        }}
      ]
    }}
  ]
}}

If the source plan doesn't specify all 7 days explicitly, infer reasonable rest/active days consistent with a realistic weekly structure. Rest days should have "is_rest": true and an empty exercises array. Output ONLY the JSON object, nothing else."""

        try:
            response = self.client.models.generate_content(
                model=MODEL_NAME,
                contents=[structuring_prompt]
            )

            raw_text = response.text.strip()

            # Defensive cleanup in case the model wraps it in a code fence anyway
            if raw_text.startswith('```'):
                raw_text = raw_text.split('```')[1]
                if raw_text.startswith('json'):
                    raw_text = raw_text[4:]
                raw_text = raw_text.strip()

            import json
            parsed = json.loads(raw_text)

            days = parsed.get('days', [])
            if len(days) != 7:
                return {
                    'success': False,
                    'error': f'Expected 7 days in structured plan, got {len(days)}. Try re-analyzing.'
                }

            return {'success': True, 'days': days}

        except json.JSONDecodeError as e:
            return {'success': False, 'error': f'AI returned invalid JSON: {str(e)}'}
        except Exception as e:
            return {'success': False, 'error': f'Weekly plan structuring failed: {str(e)}'}


def extract_section(markdown_text: str, header: str) -> str:
    """Utility to pull one '## Header' section out of the generated markdown"""
    lines = markdown_text.split('\n')
    capturing = False
    section_lines = []

    for line in lines:
        if line.strip().startswith('##'):
            if header.lower() in line.lower():
                capturing = True
                continue
            elif capturing:
                break
        if capturing:
            section_lines.append(line)

    return '\n'.join(section_lines).strip()
