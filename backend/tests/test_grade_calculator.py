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
        grades = [
            {"score": 95, "max_score": 100, "weight": 0.30},
            {"score": 88, "max_score": 100, "weight": 0.30},
            {"score": 92, "max_score": 100, "weight": 0.40},
        ]

        self.assertEqual(calculate_course_average(grades), 91.70)

    def test_non_100_max_score_case(self):
        grades = [
            GradeObject(score=45, max_score=50, weight=0.50),
            GradeObject(score=80, max_score=100, weight=0.50),
        ]

        self.assertEqual(calculate_course_average(grades), 85.00)

    def test_letter_grade_boundaries(self):
        self.assertEqual(get_letter_grade(90), "A")
        self.assertEqual(get_letter_grade(89.99), "B")
        self.assertEqual(get_letter_grade(80), "B")
        self.assertEqual(get_letter_grade(79.99), "C")
        self.assertEqual(get_letter_grade(70), "C")
        self.assertEqual(get_letter_grade(60), "D")
        self.assertEqual(get_letter_grade(59.99), "F")

    def test_overall_average(self):
        self.assertEqual(calculate_overall_average([91.7, 87.4, 96.5]), 91.87)

    def test_gpa(self):
        self.assertEqual(calculate_gpa([95, 85, 75, 65, 55]), 2.00)

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
