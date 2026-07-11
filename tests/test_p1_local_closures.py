"""Tests P1 — sentiment, bounded summary, NER generic solvers.

Covers:
  - practice-03 (sentiment mixed with contrast)
  - practice-04 (two-sentence extractive summary)
  - practice-05 (NER with single-token org, multi-token person, location)
  - variants: positive, negative, neutral, mixed, abstention cases
  - runtime validator contract for summary
  - no hardcoded task_id checks
"""
from __future__ import annotations
import pytest
from app.router.local_solvers import (
    solve_sentiment,
    solve_summary_one_sentence,
    solve_ner,
)

# ── Sentiment ─────────────────────────────────────────────────────────────────

class TestSentimentPractice:
    """practice-03 exact prompt."""
    _P03 = (
        "Classify the sentiment of this review as positive, negative, or neutral: "
        "'The battery lasts forever and the screen is gorgeous, "
        "but the keyboard feels cheap.'"
    )

    def test_practice03_closes_locally(self):
        result = solve_sentiment(self._P03)
        assert result is not None, "practice-03 should close locally"

    def test_practice03_is_mixed(self):
        result = solve_sentiment(self._P03)
        assert "mixed" in result.lower()

    def test_practice03_mentions_positive_signal(self):
        result = solve_sentiment(self._P03)
        # should mention 'gorgeous', 'lasts', or 'forever'
        assert any(w in result for w in ("gorgeous", "lasts", "forever"))

    def test_practice03_mentions_negative_signal(self):
        result = solve_sentiment(self._P03)
        assert "cheap" in result


class TestSentimentPositive:
    def test_simple_positive(self):
        r = solve_sentiment("Classify the sentiment: 'This product is excellent and amazing.'")
        assert r is not None and "positive" in r.lower()

    def test_loved_positive(self):
        r = solve_sentiment("What is the sentiment? 'I loved every moment of it.'")
        assert r is not None and "positive" in r.lower()

    def test_wonderful_positive(self):
        r = solve_sentiment("Classify sentiment: 'The experience was wonderful and enjoyable.'")
        assert r is not None and "positive" in r.lower()

    def test_gorgeous_positive_no_contrast(self):
        r = solve_sentiment("Classify the sentiment: 'The screen is gorgeous and the battery is great.'")
        assert r is not None and "positive" in r.lower()

    def test_recommended_positive(self):
        r = solve_sentiment("What sentiment? 'I highly recommended this to all my friends, it was fantastic.'")
        assert r is not None and "positive" in r.lower()


class TestSentimentNegative:
    def test_simple_negative(self):
        r = solve_sentiment("Classify the sentiment: 'This product is terrible and broken.'")
        assert r is not None and "negative" in r.lower()

    def test_hated_negative(self):
        r = solve_sentiment("What is the sentiment? 'I hated this, it was awful.'")
        assert r is not None and "negative" in r.lower()

    def test_disappointing_negative(self):
        r = solve_sentiment("Classify sentiment: 'Very disappointing, it broke after a week.'")
        assert r is not None and "negative" in r.lower()

    def test_cheap_negative(self):
        r = solve_sentiment("Classify the sentiment: 'The build quality is cheap and fragile.'")
        assert r is not None and "negative" in r.lower()

    def test_worst_negative(self):
        r = solve_sentiment("Classify the sentiment: 'Worst purchase I have ever made, terrible quality.'")
        assert r is not None and "negative" in r.lower()


class TestSentimentMixed:
    def test_mixed_but(self):
        r = solve_sentiment("Classify sentiment: 'Great camera, but the battery is terrible.'")
        assert r is not None and "mixed" in r.lower()

    def test_mixed_however(self):
        r = solve_sentiment(
            "Sentiment? 'The food was excellent. However, the service was awful.'"
        )
        assert r is not None and "mixed" in r.lower()

    def test_mixed_although(self):
        r = solve_sentiment(
            "Classify the sentiment: 'Although the performance is superb, the design is flimsy.'"
        )
        assert r is not None and "mixed" in r.lower()

    def test_mixed_though(self):
        r = solve_sentiment("What is the sentiment? 'Love the speed, though it scratches easily.'")
        assert r is not None and "mixed" in r.lower()

    def test_mixed_yet(self):
        r = solve_sentiment("Classify the sentiment: 'The display is gorgeous, yet the keyboard is awful.'")
        assert r is not None and "mixed" in r.lower()


class TestSentimentNeutral:
    def test_explicit_neutral_marker(self):
        r = solve_sentiment("Classify sentiment: 'the text is neutral and objective.'")
        assert r is not None and "neutral" in r.lower()

    def test_no_trigger_returns_none(self):
        r = solve_sentiment("What time is it?")
        assert r is None

    def test_factual_no_polarity_returns_none_without_neutral_word(self):
        r = solve_sentiment("Classify the sentiment: 'The sky is blue.'")
        assert r is None  # no polarity signals, no neutral marker


class TestSentimentAbstention:
    def test_no_trigger_abstains(self):
        assert solve_sentiment("Tell me about machine learning.") is None

    def test_contrast_without_two_polarities_abstains(self):
        # "but" present but only one polarity detectable
        assert solve_sentiment(
            "Classify: 'the product arrived, but I ordered it two days ago.'"
        ) is None

    def test_opposing_signals_without_contrast_abstains(self):
        # good + terrible without contrast marker
        assert solve_sentiment(
            "Classify: 'the screen is good and the battery is terrible.'"
        ) is None

    def test_single_ambiguous_word_abstains(self):
        # "fine" is not in lexicon → abstain
        assert solve_sentiment("Classify: 'It is fine.'") is None

    def test_no_polarity_no_neutral_abstains(self):
        assert solve_sentiment(
            "Classify the sentiment: 'The device was delivered yesterday.'"
        ) is None


# ── Bounded summary ───────────────────────────────────────────────────────────

_P04_PASSAGE = (
    "Solar panels convert sunlight into electricity using photovoltaic cells. "
    "Over the past decade, their cost has fallen by more than 80 percent, "
    "making them one of the cheapest sources of new electricity in many countries. "
    "However, their output varies with weather and daylight, so grids that rely "
    "heavily on solar power need storage or backup generation to remain stable."
)
_P04_PROMPT = f"Summarize the following passage in two sentences: '{_P04_PASSAGE}'"


class TestSummaryPractice:
    def test_practice04_closes_locally(self):
        r = solve_summary_one_sentence(_P04_PROMPT)
        assert r is not None, "practice-04 should close locally"

    def test_practice04_has_two_sentences(self):
        r = solve_summary_one_sentence(_P04_PROMPT)
        # Count sentence-ending punctuation followed by space+capital or end
        import re
        sents = re.split(r"(?<=[.!?])\s+", r.strip())
        assert len(sents) == 2, f"Expected 2 sentences, got {len(sents)}: {r!r}"

    def test_practice04_mentions_solar(self):
        r = solve_summary_one_sentence(_P04_PROMPT)
        assert "solar" in r.lower() or "photovoltaic" in r.lower()

    def test_practice04_no_invented_content(self):
        r = solve_summary_one_sentence(_P04_PROMPT)
        # Simple heuristic: response words should mostly appear in passage
        passage_words = set(_P04_PASSAGE.lower().split())
        resp_words = set(r.lower().split())
        invented = resp_words - passage_words - {
            "the", "a", "an", "and", "or", "but", "in", "of", "to",
            "is", "are", "was", "were", "that", "this", "it", "its",
            "as", "by", "for", "on", "at", "with", "from", "have",
        }
        # Allow up to 5 words not in passage (punctuation artefacts, etc.)
        assert len(invented) <= 5, f"Too many invented words: {invented}"

    def test_practice04_not_empty(self):
        r = solve_summary_one_sentence(_P04_PROMPT)
        assert r and r.strip()


class TestSummaryOnesentence:
    def test_one_sentence_old_pattern(self):
        text = (
            "The Eiffel Tower is a famous landmark in Paris. "
            "It was built in 1889. Many tourists visit it each year."
        )
        r = solve_summary_one_sentence(f"Summarize in one sentence: '{text}'")
        assert r is not None
        import re
        sents = re.split(r"(?<=[.!?])\s+", r.strip())
        assert len(sents) == 1

    def test_two_sentences_generic_contrast(self):
        text = (
            "Electric cars produce zero direct emissions. "
            "However, the electricity used to charge them may come from fossil fuels, "
            "so the net benefit depends on the local energy mix."
        )
        r = solve_summary_one_sentence(f"Summarize the following passage in two sentences: '{text}'")
        assert r is not None
        import re
        sents = re.split(r"(?<=[.!?])\s+", r.strip())
        assert len(sents) == 2

    def test_two_sentences_no_contrast(self):
        text = (
            "Coffee is a popular beverage consumed worldwide. "
            "It is made from roasted coffee beans. "
            "Many people drink it in the morning to feel alert."
        )
        r = solve_summary_one_sentence(f"Summarize in two sentences: '{text}'")
        assert r is not None

    def test_too_short_abstains(self):
        assert solve_summary_one_sentence("Summarize in one sentence: 'Hi.'") is None

    def test_no_pattern_abstains(self):
        assert solve_summary_one_sentence("Tell me about solar panels.") is None

    def test_passage_fewer_sents_than_n_abstains(self):
        # Only one sentence in passage but requesting two
        text = "Solar panels convert sunlight into electricity."
        r = solve_summary_one_sentence(f"Summarize in two sentences: '{text}'")
        assert r is None


# ── NER ───────────────────────────────────────────────────────────────────────

_P05_PROMPT = (
    "Extract all named entities (people, organizations, locations) from this "
    "sentence: 'Satya Nadella announced that Microsoft will open a new research "
    "lab in Nairobi in partnership with the University of Cambridge.'"
)


class TestNERPractice:
    def test_practice05_closes_locally(self):
        r = solve_ner(_P05_PROMPT)
        assert r is not None, "practice-05 should close locally"

    def test_practice05_has_satya_nadella_person(self):
        r = solve_ner(_P05_PROMPT)
        assert "Satya Nadella" in r

    def test_practice05_has_microsoft_org(self):
        r = solve_ner(_P05_PROMPT)
        assert "Microsoft" in r

    def test_practice05_has_nairobi_location(self):
        r = solve_ner(_P05_PROMPT)
        assert "Nairobi" in r

    def test_practice05_has_university_of_cambridge_org(self):
        r = solve_ner(_P05_PROMPT)
        assert "University of Cambridge" in r

    def test_practice05_order(self):
        r = solve_ner(_P05_PROMPT)
        assert r.index("Satya Nadella") < r.index("Microsoft")
        assert r.index("Microsoft") < r.index("Nairobi")


class TestNERPerson:
    def test_two_token_person(self):
        r = solve_ner(
            "Extract all named entities from this sentence: 'Marie Curie won the Nobel Prize.'"
        )
        assert r is not None and "Marie Curie" in r and "PERSON" in r

    def test_three_token_person(self):
        r = solve_ner(
            "Extract named entities from: 'Martin Luther King delivered the speech.'"
        )
        assert r is not None and "Martin Luther King" in r

    def test_single_first_name_abstains(self):
        # Single capitalized token with no org/place match → abstain
        r = solve_ner("Extract entities from: 'Xylophorus visited Qbrtz.'")
        assert r is None


class TestNEROrganization:
    def test_org_with_suffix(self):
        r = solve_ner(
            "Extract named entities from: 'OpenAI Labs released a new model.'"
        )
        assert r is not None and "ORGANIZATION" in r

    def test_single_token_known_org(self):
        r = solve_ner(
            "Extract all named entities from: 'Google acquired the startup.'"
        )
        assert r is not None and "Google" in r and "ORGANIZATION" in r

    def test_university_with_of(self):
        r = solve_ner(
            "Extract entities from: 'The University of Toronto hosted the event.'"
        )
        assert r is not None and "University of Toronto" in r and "ORGANIZATION" in r


class TestNERLocation:
    def test_known_city(self):
        r = solve_ner(
            "Extract all named entities from: 'The summit took place in Paris.'"
        )
        assert r is not None and "Paris" in r and "LOCATION" in r

    def test_known_country(self):
        r = solve_ner(
            "Extract named entities from: 'The company expanded to Japan and France.'"
        )
        assert r is not None and "Japan" in r and "France" in r


class TestNERAbstention:
    def test_no_trigger_abstains(self):
        assert solve_ner("What is the capital of France?") is None

    def test_unclassifiable_single_token_abstains(self):
        r = solve_ner(
            "Extract all named entities from: 'Qbrtzx announced a new product.'"
        )
        assert r is None

    def test_empty_sentence_abstains(self):
        assert solve_ner("Extract named entities from: ''") is None


# ── Runtime validator contract for summary ────────────────────────────────────

class TestSummaryRuntimeContract:
    """Verify the runtime contract: exact sentence count, non-empty, no markup."""

    def _count_sentences(self, text: str) -> int:
        import re
        parts = re.split(r"(?<=[.!?])\s+", text.strip())
        return len([p for p in parts if p])

    def test_one_sentence_result_has_exactly_one(self):
        text = (
            "The Eiffel Tower is a famous landmark in Paris. "
            "It attracts millions of visitors each year."
        )
        r = solve_summary_one_sentence(f"Summarize in one sentence: '{text}'")
        assert r is not None
        assert self._count_sentences(r) == 1

    def test_two_sentence_result_has_exactly_two(self):
        r = solve_summary_one_sentence(_P04_PROMPT)
        assert r is not None
        assert self._count_sentences(r) == 2

    def test_no_html_markup(self):
        r = solve_summary_one_sentence(_P04_PROMPT)
        assert r is not None
        assert "<" not in r and ">" not in r

    def test_result_bounded_length(self):
        r = solve_summary_one_sentence(_P04_PROMPT)
        assert r is not None
        assert len(r) < 1500  # hard cap from _SUMMARY_MAX_CHARS * 2 + separator
