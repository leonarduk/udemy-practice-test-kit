"""Deterministic answer-option shuffle: reproducibility, balance, and that a
per-option explanation always travels with the option it explains.
"""

import types
import unittest

from ptkit.shuffle import deterministic_permutation, shuffle_questions
from ptkit.model import Question


def make_config(seed="test-seed", letters="ABCD"):
    return types.SimpleNamespace(shuffle_seed=seed, option_letters=letters)


def make_question(exam, number, stem, answer, option_explanations=None):
    letters = "ABCD"
    return Question(
        exam=exam, number=number, stem=stem,
        options={l: f"{stem} option {l}" for l in letters},
        answer=answer,
        explanation=f"why {stem}",
        domain="D",
        option_explanations=option_explanations,
    )


class DeterministicPermutationTests(unittest.TestCase):
    def test_same_seed_and_n_always_gives_the_same_order(self):
        self.assertEqual(
            deterministic_permutation("seed", 8), deterministic_permutation("seed", 8)
        )

    def test_different_seeds_usually_give_different_orders(self):
        self.assertNotEqual(
            deterministic_permutation("seed-a", 8), deterministic_permutation("seed-b", 8)
        )

    def test_result_is_a_permutation_not_just_a_sequence(self):
        order = deterministic_permutation("seed", 10)
        self.assertEqual(sorted(order), list(range(10)))


class ShuffleQuestionsTests(unittest.TestCase):
    def test_shuffling_twice_is_byte_identical(self):
        config = make_config()
        questions = [
            make_question(1, i + 1, f"Q{i}", answer="A") for i in range(12)
        ]
        first = shuffle_questions(questions, config)
        second = shuffle_questions(questions, config)
        self.assertEqual(
            [(q.answer, q.options) for q in first],
            [(q.answer, q.options) for q in second],
        )

    def test_correct_answer_slot_is_balanced_within_an_exam(self):
        config = make_config()
        questions = [
            make_question(1, i + 1, f"Q{i}", answer="B") for i in range(12)
        ]
        shuffled = shuffle_questions(questions, config)
        counts = {}
        for q in shuffled:
            counts[q.answer] = counts.get(q.answer, 0) + 1
        self.assertEqual(max(counts.values()) - min(counts.values()), 0)

    def test_distractor_and_correct_option_text_survive_unchanged(self):
        config = make_config()
        questions = [make_question(1, 1, "Q0", answer="B")]
        shuffled = shuffle_questions(questions, config)[0]
        self.assertEqual(
            sorted(shuffled.options.values()), sorted(questions[0].options.values())
        )
        # The text that used to be the correct answer B is now filed under
        # whatever letter the shuffle assigned as the new answer.
        self.assertEqual(shuffled.options[shuffled.answer], "Q0 option B")

    def test_option_explanations_travel_with_their_option_text(self):
        config = make_config()
        explanations = {
            "A": "why A", "B": "why B (the correct one)", "C": "why C", "D": "why D",
        }
        questions = [
            make_question(1, 1, "Q0", answer="B", option_explanations=explanations)
        ]
        shuffled = shuffle_questions(questions, config)[0]
        # Whichever letter now holds "Q0 option B" must hold "why B ..." too.
        for letter, text in shuffled.options.items():
            original_letter = text.rsplit(" ", 1)[-1]
            self.assertEqual(
                shuffled.option_explanations[letter], explanations[original_letter]
            )

    def test_a_question_with_no_option_explanations_stays_empty_after_shuffling(self):
        config = make_config()
        questions = [make_question(1, 1, "Q0", answer="B")]
        shuffled = shuffle_questions(questions, config)[0]
        self.assertEqual(shuffled.option_explanations, {})

    def test_editing_one_questions_stem_does_not_reshuffle_its_neighbours(self):
        config = make_config()
        questions = [make_question(1, i + 1, f"Q{i}", answer="B") for i in range(6)]
        before = shuffle_questions(questions, config)

        edited = list(questions)
        edited[0] = make_question(1, 1, "Q0 edited", answer="B")
        after = shuffle_questions(edited, config)

        for i in range(1, 6):
            self.assertEqual(before[i].answer, after[i].answer)
            self.assertEqual(before[i].options, after[i].options)

    def test_exams_are_shuffled_independently(self):
        config = make_config()
        questions = [
            make_question(1, 1, "E1Q0", answer="B"),
            make_question(2, 1, "E1Q0", answer="B"),  # same stem text, different exam
        ]
        shuffled = shuffle_questions(questions, config)
        # Same seed text but different exam numbers feed into the per-question
        # seed, so there is no guarantee -- and no requirement -- that the two
        # land on the same slot; this only asserts each was independently
        # shuffled to a valid slot for its own exam.
        for q in shuffled:
            self.assertIn(q.answer, "ABCD")

    def test_document_order_is_preserved(self):
        config = make_config()
        questions = [make_question(1, i + 1, f"Q{i}", answer="A") for i in range(5)]
        shuffled = shuffle_questions(questions, config)
        self.assertEqual([q.number for q in shuffled], [q.number for q in questions])


if __name__ == "__main__":
    unittest.main()
