import os
import tempfile
import unittest
from datetime import datetime, timedelta

from app import database

class TestStats(unittest.TestCase):
    def setUp(self):
        self.temp_file = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.temp_file.name
        self.temp_file.close()
        os.environ["DB_PATH"] = self.db_path
        database.init_db()

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_empty_stats(self):
        stats = database.get_stats(days=30)
        summary = stats["summary"]
        self.assertEqual(summary["total_logs"], 0)
        self.assertEqual(summary["active_days"], 0)
        self.assertEqual(summary["avg_daily_count"], 0.0)
        self.assertIsNone(summary["avg_bristol"])
        self.assertIsNone(summary["avg_pain"])
        self.assertEqual(summary["blood_incidence_pct"], 0.0)

    def test_stats_active_days_only(self):
        today = datetime.now()
        yesterday = today - timedelta(days=1)
        today_str = today.strftime("%Y-%m-%d")
        yesterday_str = yesterday.strftime("%Y-%m-%d")

        # 3 logs on today
        database.add_log(bristol=4, pain=2, blood="none", custom_timestamp=f"{today_str} 08:00:00")
        database.add_log(bristol=5, pain=3, blood="none", custom_timestamp=f"{today_str} 12:00:00")
        database.add_log(bristol=4, pain=1, blood="some", custom_timestamp=f"{today_str} 18:00:00")

        # 3 logs on yesterday
        database.add_log(bristol=3, pain=4, blood="none", custom_timestamp=f"{yesterday_str} 09:00:00")
        database.add_log(bristol=4, pain=2, blood="alot", custom_timestamp=f"{yesterday_str} 14:00:00")
        database.add_log(bristol=4, pain=2, blood="none", custom_timestamp=f"{yesterday_str} 20:00:00")

        stats = database.get_stats(days=30)
        summary = stats["summary"]

        self.assertEqual(summary["total_logs"], 6)
        self.assertEqual(summary["active_days"], 2)
        self.assertEqual(summary["days_window"], 30)
        # Average frequency must be 6 / 2 = 3.0 movements per active day, NOT 6 / 30 = 0.2
        self.assertEqual(summary["avg_daily_count"], 3.0)
        self.assertEqual(summary["avg_bristol"], 4.0)
        self.assertEqual(summary["avg_pain"], 2.33)
        self.assertEqual(summary["blood_events"]["none"], 4)
        self.assertEqual(summary["blood_events"]["some"], 1)
        self.assertEqual(summary["blood_events"]["alot"], 1)
        self.assertEqual(summary["blood_incidence_pct"], round((2 / 6) * 100, 1))

    def test_stats_single_active_day(self):
        today_str = datetime.now().strftime("%Y-%m-%d")
        database.add_log(bristol=4, pain=1, blood="none", custom_timestamp=f"{today_str} 10:00:00")
        database.add_log(bristol=6, pain=5, blood="some", custom_timestamp=f"{today_str} 16:00:00")

        stats = database.get_stats(days=14)
        summary = stats["summary"]
        self.assertEqual(summary["total_logs"], 2)
        self.assertEqual(summary["active_days"], 1)
        self.assertEqual(summary["avg_daily_count"], 2.0)
        self.assertEqual(len(stats["daily_breakdown"]), 1)
        self.assertEqual(stats["daily_breakdown"][0]["date"], today_str)
        self.assertEqual(stats["daily_breakdown"][0]["count"], 2)

if __name__ == "__main__":
    unittest.main()
