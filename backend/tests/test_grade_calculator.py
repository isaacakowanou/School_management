import unittest

from services.grade_calculator import (
    calculate_course_average,
    calculate_gpa,
    calculate_overall_average,
    get_letter_grade,
)


class GradeObject:
    def __init__(self, score, max_score, weight):
        self.score = score
        self.max_score = max_score
        self.weight = weight


class GradeCalculatorTests(unittest.TestCase):
    def test_weighted_average_normal_case(self):
        # On the /20 scale: 19.0*.3 + 17.6*.3 + 18.4*.4 = 18.34
        grades = [
            {"score": 95, "max_score": 100, "weight": 0.30},
            {"score": 88, "max_score": 100, "weight": 0.30},
            {"score": 92, "max_score": 100, "weight": 0.40},
        ]

        self.assertEqual(calculate_course_average(grades), 18.34)

    def test_non_100_max_score_case(self):
        # 45/50 -> 18/20, 80/100 -> 16/20, equal weights -> 17.00
        grades = [
            GradeObject(score=45, max_score=50, weight=0.50),
            GradeObject(score=80, max_score=100, weight=0.50),
        ]

        self.assertEqual(calculate_course_average(grades), 17.00)

    def test_score_15_of_20_contributes_15_when_weight_one(self):
        grades = [{"score": 15, "max_score": 20, "weight": 1.0}]
        self.assertEqual(calculate_course_average(grades), 15.00)

    def test_score_5_of_10_normalizes_to_10_of_20(self):
        grades = [{"score": 5, "max_score": 10, "weight": 1.0}]
        self.assertEqual(calculate_course_average(grades), 10.00)

    def test_mixed_max_scores_weighted_average_on_20_scale(self):
        # 15/20 -> 15, 5/10 -> 10/20, equal weights -> 12.50
        grades = [
            {"score": 15, "max_score": 20, "weight": 0.50},
            {"score": 5, "max_score": 10, "weight": 0.50},
        ]
        self.assertEqual(calculate_course_average(grades), 12.50)

    def test_course_average_stays_within_0_to_20(self):
        self.assertEqual(calculate_course_average([{"score": 20, "max_score": 20, "weight": 1.0}]), 20.00)
        self.assertEqual(calculate_course_average([{"score": 0, "max_score": 20, "weight": 1.0}]), 0.00)

    def test_letter_grade_bisc_lower_bounds(self):
        # Each grade at exactly its lower boundary.
        self.assertEqual(get_letter_grade(20.0), "A+")
        self.assertEqual(get_letter_grade(19.0), "A+")
        self.assertEqual(get_letter_grade(17.0), "A")
        self.assertEqual(get_letter_grade(15.0), "B+")
        self.assertEqual(get_letter_grade(13.0), "B")
        self.assertEqual(get_letter_grade(11.0), "C+")
        self.assertEqual(get_letter_grade(9.0), "C")
        self.assertEqual(get_letter_grade(7.0), "D")
        self.assertEqual(get_letter_grade(4.0), "E")
        self.assertEqual(get_letter_grade(0.0), "F")

    def test_letter_grade_bisc_just_below_boundaries(self):
        self.assertEqual(get_letter_grade(18.9), "A")
        self.assertEqual(get_letter_grade(16.9), "B+")
        self.assertEqual(get_letter_grade(14.9), "B")
        self.assertEqual(get_letter_grade(12.9), "C+")
        self.assertEqual(get_letter_grade(10.9), "C")
        self.assertEqual(get_letter_grade(8.9), "D")
        self.assertEqual(get_letter_grade(6.9), "E")
        self.assertEqual(get_letter_grade(4.9), "E")
        self.assertEqual(get_letter_grade(3.9), "F")

    def test_letter_grade_bisc_fractional(self):
        self.assertEqual(get_letter_grade(16.5), "B+")
        self.assertEqual(get_letter_grade(17.5), "A")

    def test_overall_average(self):
        # Arithmetic mean of /20 course averages.
        self.assertEqual(calculate_overall_average([18.0, 17.0, 19.0]), 18.0)

    def test_gpa(self):
        # /20 averages -> letters A,B,C,D,F via the bridge -> 4,3,2,1,0 -> 2.00
        self.assertEqual(calculate_gpa([19, 17, 15, 13, 11]), 2.00)

    def test_empty_grade_list_raises_value_error(self):
        with self.assertRaisesRegex(ValueError, "grades list cannot be empty"):
            calculate_course_average([])

    def test_empty_course_average_list_raises_value_error(self):
        with self.assertRaisesRegex(ValueError, "course averages list cannot be empty"):
            calculate_overall_average([])

        with self.assertRaisesRegex(ValueError, "course averages list cannot be empty"):
            calculate_gpa([])

    def test_weight_total_not_equal_to_one_raises_value_error(self):
        grades = [
            {"score": 95, "max_score": 100, "weight": 0.30},
            {"score": 88, "max_score": 100, "weight": 0.30},
        ]

        with self.assertRaisesRegex(ValueError, "grade weights must total 1.0"):
            calculate_course_average(grades)

    def test_score_above_max_score_raises_value_error(self):
        grades = [{"score": 105, "max_score": 100, "weight": 1.0}]

        with self.assertRaisesRegex(ValueError, "score cannot be greater than max_score"):
            calculate_course_average(grades)

    def test_negative_score_raises_value_error(self):
        grades = [{"score": -1, "max_score": 100, "weight": 1.0}]

        with self.assertRaisesRegex(ValueError, "score must be greater than or equal to 0"):
            calculate_course_average(grades)

    def test_max_score_less_than_or_equal_to_zero_raises_value_error(self):
        grades = [{"score": 0, "max_score": 0, "weight": 1.0}]

        with self.assertRaisesRegex(ValueError, "max_score must be greater than 0"):
            calculate_course_average(grades)


if __name__ == "__main__":
    unittest.main()
