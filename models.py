"""
Solo Leveling Fitness - Database Models
Comprehensive models for user progression, exercises, and social features
"""

from datetime import datetime, timedelta
from typing import List, Dict, Optional
import sqlite3
import json
import hashlib
import secrets


class Database:
    """Main database handler for the Solo Leveling Fitness System"""
    
    def __init__(self, db_path: str = "fitness_hunter.db"):
        self.db_path = db_path
        self.init_database()
    
    def get_connection(self):
        """Create a new database connection"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def init_database(self):
        """Initialize all database tables"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Users table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login TIMESTAMP
            )
        ''')
        
        # Player stats table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS player_stats (
                user_id INTEGER PRIMARY KEY,
                age INTEGER,
                height_cm REAL,
                weight_kg REAL,
                initial_height REAL,
                initial_weight REAL,
                target_height REAL,
                target_weight REAL,
                level INTEGER DEFAULT 1,
                exp INTEGER DEFAULT 0,
                exp_to_next_level INTEGER DEFAULT 100,
                stat_points INTEGER DEFAULT 0,
                strength INTEGER DEFAULT 10,
                endurance INTEGER DEFAULT 10,
                agility INTEGER DEFAULT 10,
                vitality INTEGER DEFAULT 10,
                primary_focus_areas TEXT,
                experience_level TEXT DEFAULT 'beginner',
                days_per_week INTEGER DEFAULT 5,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        ''')

        
        # Exercise records table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS exercise_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                exercise_name TEXT NOT NULL,
                category TEXT NOT NULL,
                max_reps INTEGER DEFAULT 0,
                max_weight_kg REAL DEFAULT 0,
                max_duration_seconds INTEGER DEFAULT 0,
                personal_record INTEGER DEFAULT 0,
                difficulty_level INTEGER DEFAULT 1,
                last_performed TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        ''')
        
        # Daily quests table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS daily_quests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                quest_date DATE NOT NULL,
                quest_data TEXT NOT NULL,
                completed BOOLEAN DEFAULT 0,
                exp_reward INTEGER DEFAULT 0,
                completed_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        ''')
        
        # Quest completions table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS quest_completions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                quest_id INTEGER,
                exercise_name TEXT,
                reps_completed INTEGER,
                sets_completed INTEGER,
                weight_used REAL,
                duration_seconds INTEGER,
                completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (quest_id) REFERENCES daily_quests(id)
            )
        ''')
        
        # Workout history table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS workout_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                workout_date DATE NOT NULL,
                total_exercises INTEGER DEFAULT 0,
                total_reps INTEGER DEFAULT 0,
                total_duration_minutes INTEGER DEFAULT 0,
                exp_gained INTEGER DEFAULT 0,
                calories_burned INTEGER DEFAULT 0,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        ''')
        
        # Goals table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS goals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                goal_type TEXT NOT NULL,
                goal_name TEXT NOT NULL,
                target_value REAL,
                current_value REAL DEFAULT 0,
                deadline DATE,
                priority TEXT DEFAULT 'medium',
                status TEXT DEFAULT 'active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        ''')
        
        # Friends table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS friends (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                friend_id INTEGER,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                accepted_at TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (friend_id) REFERENCES users(id)
            )
        ''')
        
        # Achievements table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS achievements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                achievement_name TEXT NOT NULL,
                achievement_type TEXT NOT NULL,
                description TEXT,
                exp_reward INTEGER DEFAULT 0,
                unlocked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        ''')
        
        # Rest days table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS rest_schedule (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                rest_day DATE NOT NULL,
                reason TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        ''')
        
        # Physique analysis / Quest Log table (target-based AI training plans)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS physique_quests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                target_name TEXT,
                source_type TEXT DEFAULT 'text',
                image_path TEXT,
                physique_breakdown TEXT,
                quest_log_markdown TEXT NOT NULL,
                is_active BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        ''')
        
        # Structured weekly training split, parsed out of a physique Quest Log's
        # "Main Story Quests" section so it can drive the actual daily quests
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS weekly_training_plan (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                physique_quest_id INTEGER,
                day_of_week INTEGER NOT NULL,
                day_label TEXT,
                focus TEXT,
                is_rest BOOLEAN DEFAULT 0,
                exercises_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (physique_quest_id) REFERENCES physique_quests(id)
            )
        ''')
        
        # Per-user AI API keys (encrypted at rest) so a deployed multi-user
        # site doesn't have to foot everyone's AI usage on one shared key
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_settings (
                user_id INTEGER PRIMARY KEY,
                encrypted_gemini_key TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        ''')
        
        conn.commit()
        conn.close()
        
        # Lightweight migration for existing DBs created before these columns existed
        self._migrate_schema()
    
    def _migrate_schema(self):
        """Add new columns to existing databases without wiping data"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("PRAGMA table_info(player_stats)")
        existing_cols = {row['name'] for row in cursor.fetchall()}
        
        migrations = {
            'primary_focus_areas': "ALTER TABLE player_stats ADD COLUMN primary_focus_areas TEXT",
            'experience_level': "ALTER TABLE player_stats ADD COLUMN experience_level TEXT DEFAULT 'beginner'",
            'days_per_week': "ALTER TABLE player_stats ADD COLUMN days_per_week INTEGER DEFAULT 5"
        }
        
        for col, sql in migrations.items():
            if col not in existing_cols:
                try:
                    cursor.execute(sql)
                except sqlite3.OperationalError:
                    pass
        
        conn.commit()
        conn.close()


class User:
    """User authentication and management"""
    
    def __init__(self, db: Database):
        self.db = db
    
    def hash_password(self, password: str) -> str:
        """Hash password using SHA-256"""
        return hashlib.sha256(password.encode()).hexdigest()
    
    def create_user(self, username: str, email: str, password: str) -> Optional[int]:
        """Create a new user account"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        try:
            password_hash = self.hash_password(password)
            cursor.execute(
                'INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)',
                (username, email, password_hash)
            )
            conn.commit()
            user_id = cursor.lastrowid
            conn.close()
            return user_id
        except sqlite3.IntegrityError:
            conn.close()
            return None
    
    def authenticate(self, username: str, password: str) -> Optional[Dict]:
        """Authenticate user and return user data"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        password_hash = self.hash_password(password)
        cursor.execute(
            'SELECT * FROM users WHERE username = ? AND password_hash = ?',
            (username, password_hash)
        )
        user = cursor.fetchone()
        
        if user:
            cursor.execute(
                'UPDATE users SET last_login = ? WHERE id = ?',
                (datetime.now(), user['id'])
            )
            conn.commit()
            conn.close()
            return dict(user)
        
        conn.close()
        return None
    
    def get_user_by_id(self, user_id: int) -> Optional[Dict]:
        """Get user by ID"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
        user = cursor.fetchone()
        conn.close()
        return dict(user) if user else None


class PlayerStats:
    """Player statistics and progression management"""
    
    def __init__(self, db: Database):
        self.db = db
    
    def create_player_stats(self, user_id: int, age: int, height_cm: float, 
                           weight_kg: float, target_height: float = None,
                           target_weight: float = None,
                           primary_focus_areas: List[str] = None,
                           experience_level: str = 'beginner',
                           days_per_week: int = 5) -> bool:
        """Create initial player stats"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT INTO player_stats 
                (user_id, age, height_cm, weight_kg, initial_height, initial_weight,
                 target_height, target_weight, primary_focus_areas, experience_level,
                 days_per_week)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (user_id, age, height_cm, weight_kg, height_cm, weight_kg,
                  target_height or height_cm, target_weight or weight_kg,
                  json.dumps(primary_focus_areas or []), experience_level,
                  days_per_week))
            conn.commit()
            conn.close()
            return True
        except sqlite3.IntegrityError:
            conn.close()
            return False
    
    def get_primary_focus_areas(self, user_id: int) -> List[str]:
        """Get the user's selected primary objective paths (multi-select goals)"""
        stats = self.get_player_stats(user_id)
        if not stats or not stats.get('primary_focus_areas'):
            return []
        try:
            return json.loads(stats['primary_focus_areas'])
        except (json.JSONDecodeError, TypeError):
            return []
    
    def update_primary_focus_areas(self, user_id: int, focus_areas: List[str]) -> bool:
        """Update the user's selected primary objective paths"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE player_stats 
            SET primary_focus_areas = ?, updated_at = ?
            WHERE user_id = ?
        ''', (json.dumps(focus_areas), datetime.now(), user_id))
        
        conn.commit()
        conn.close()
        return True
    
    def get_player_stats(self, user_id: int) -> Optional[Dict]:
        """Get player stats"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM player_stats WHERE user_id = ?', (user_id,))
        stats = cursor.fetchone()
        conn.close()
        return dict(stats) if stats else None
    
    def add_exp(self, user_id: int, exp_amount: int) -> Dict:
        """Add experience and handle leveling up"""
        stats = self.get_player_stats(user_id)
        if not stats:
            return {'leveled_up': False}
        
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        new_exp = stats['exp'] + exp_amount
        level = stats['level']
        exp_to_next = stats['exp_to_next_level']
        leveled_up = False
        levels_gained = 0
        stat_points = stats['stat_points']
        
        # Check for level ups
        while new_exp >= exp_to_next:
            new_exp -= exp_to_next
            level += 1
            levels_gained += 1
            stat_points += 5  # 5 stat points per level
            exp_to_next = int(exp_to_next * 1.15)  # 15% increase per level
            leveled_up = True
        
        cursor.execute('''
            UPDATE player_stats 
            SET exp = ?, level = ?, exp_to_next_level = ?, stat_points = ?, updated_at = ?
            WHERE user_id = ?
        ''', (new_exp, level, exp_to_next, stat_points, datetime.now(), user_id))
        
        conn.commit()
        conn.close()
        
        return {
            'leveled_up': leveled_up,
            'levels_gained': levels_gained,
            'new_level': level,
            'current_exp': new_exp,
            'exp_to_next': exp_to_next,
            'stat_points': stat_points
        }
    
    def allocate_stat_points(self, user_id: int, strength: int = 0, 
                            endurance: int = 0, agility: int = 0, 
                            vitality: int = 0) -> bool:
        """Allocate stat points"""
        stats = self.get_player_stats(user_id)
        if not stats:
            return False
        
        total_points = strength + endurance + agility + vitality
        if total_points > stats['stat_points']:
            return False
        
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE player_stats 
            SET strength = strength + ?, 
                endurance = endurance + ?,
                agility = agility + ?,
                vitality = vitality + ?,
                stat_points = stat_points - ?,
                updated_at = ?
            WHERE user_id = ?
        ''', (strength, endurance, agility, vitality, total_points, 
              datetime.now(), user_id))
        
        conn.commit()
        conn.close()
        return True
    
    def update_body_measurements(self, user_id: int, height_cm: float = None,
                                 weight_kg: float = None) -> bool:
        """Update body measurements"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        updates = []
        params = []
        
        if height_cm is not None:
            updates.append('height_cm = ?')
            params.append(height_cm)
        
        if weight_kg is not None:
            updates.append('weight_kg = ?')
            params.append(weight_kg)
        
        if not updates:
            return False
        
        updates.append('updated_at = ?')
        params.append(datetime.now())
        params.append(user_id)
        
        query = f"UPDATE player_stats SET {', '.join(updates)} WHERE user_id = ?"
        cursor.execute(query, params)
        
        conn.commit()
        conn.close()
        return True


class ExerciseManager:
    """Exercise tracking and progression"""
    
    def __init__(self, db: Database):
        self.db = db
    
    def add_or_update_exercise(self, user_id: int, exercise_name: str,
                               category: str, max_reps: int = 0,
                               max_weight_kg: float = 0,
                               max_duration_seconds: int = 0) -> bool:
        """Add or update exercise record"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        # Check if exercise exists
        cursor.execute('''
            SELECT id, personal_record FROM exercise_records 
            WHERE user_id = ? AND exercise_name = ?
        ''', (user_id, exercise_name))
        existing = cursor.fetchone()
        
        if existing:
            # Update if new personal record
            new_pr = max(max_reps, max_duration_seconds)
            old_pr = existing['personal_record']
            
            cursor.execute('''
                UPDATE exercise_records 
                SET max_reps = ?, max_weight_kg = ?, max_duration_seconds = ?,
                    personal_record = ?, last_performed = ?
                WHERE id = ?
            ''', (max(max_reps, cursor.execute('SELECT max_reps FROM exercise_records WHERE id = ?', 
                  (existing['id'],)).fetchone()[0]),
                  max_weight_kg, max_duration_seconds, max(new_pr, old_pr),
                  datetime.now(), existing['id']))
        else:
            # Insert new exercise
            cursor.execute('''
                INSERT INTO exercise_records 
                (user_id, exercise_name, category, max_reps, max_weight_kg,
                 max_duration_seconds, personal_record, last_performed)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (user_id, exercise_name, category, max_reps, max_weight_kg,
                  max_duration_seconds, max(max_reps, max_duration_seconds),
                  datetime.now()))
        
        conn.commit()
        conn.close()
        return True
    
    def get_user_exercises(self, user_id: int) -> List[Dict]:
        """Get all exercises for a user"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM exercise_records WHERE user_id = ?
            ORDER BY category, exercise_name
        ''', (user_id,))
        exercises = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return exercises
    
    def get_exercise_by_name(self, user_id: int, exercise_name: str) -> Optional[Dict]:
        """Get specific exercise record"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM exercise_records 
            WHERE user_id = ? AND exercise_name = ?
        ''', (user_id, exercise_name))
        exercise = cursor.fetchone()
        conn.close()
        return dict(exercise) if exercise else None


class WeeklyPlanManager:
    """
    Stores and serves the structured weekly training split generated from
    an active "Become Like..." physique Quest Log, so the daily quest
    generator can build each day's quest directly from that plan instead
    of the generic algorithmic exercise picker.
    """

    def __init__(self, db: Database):
        self.db = db

    def save_weekly_plan(self, user_id: int, physique_quest_id: int,
                          days: List[Dict]) -> bool:
        """
        Replace the user's active weekly plan. `days` is a list of dicts:
        {day_of_week: 0-6 (Mon-Sun), day_label, focus, is_rest, exercises: [...]}
        """
        conn = self.db.get_connection()
        cursor = conn.cursor()

        # Clear any previous plan (only one active build-goal plan at a time)
        cursor.execute('DELETE FROM weekly_training_plan WHERE user_id = ?', (user_id,))

        for day in days:
            cursor.execute('''
                INSERT INTO weekly_training_plan
                (user_id, physique_quest_id, day_of_week, day_label, focus,
                 is_rest, exercises_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (user_id, physique_quest_id, day.get('day_of_week'),
                  day.get('day_label'), day.get('focus'),
                  1 if day.get('is_rest') else 0,
                  json.dumps(day.get('exercises', []))))

        conn.commit()
        conn.close()
        return True

    def get_plan_for_today(self, user_id: int) -> Optional[Dict]:
        """Get today's entry from the user's active weekly plan, if one exists"""
        today_weekday = datetime.now().weekday()  # Monday=0 ... Sunday=6

        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM weekly_training_plan
            WHERE user_id = ? AND day_of_week = ?
            ORDER BY created_at DESC LIMIT 1
        ''', (user_id, today_weekday))
        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        result = dict(row)
        try:
            result['exercises'] = json.loads(result['exercises_json'])
        except (json.JSONDecodeError, TypeError):
            result['exercises'] = []
        return result

    def has_active_plan(self, user_id: int) -> bool:
        """Check whether the user currently has any structured weekly plan saved"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) as cnt FROM weekly_training_plan WHERE user_id = ?',
                       (user_id,))
        count = cursor.fetchone()['cnt']
        conn.close()
        return count > 0

    def clear_plan(self, user_id: int) -> bool:
        """Remove the user's weekly plan (e.g. when they deactivate a build goal)"""
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM weekly_training_plan WHERE user_id = ?', (user_id,))
        conn.commit()
        conn.close()
        return True


class UserSettings:
    """
    Per-user settings, primarily their personal AI API key so a deployed,
    multi-user site doesn't require the site owner to pay for everyone's
    AI usage on one shared key. Keys are encrypted at rest.
    """

    def __init__(self, db: Database):
        self.db = db

    def save_gemini_key(self, user_id: int, plaintext_key: str) -> bool:
        """Encrypt and store the user's personal Gemini API key"""
        from crypto_utils import encrypt_value

        encrypted = encrypt_value(plaintext_key)

        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO user_settings (user_id, encrypted_gemini_key, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                encrypted_gemini_key = excluded.encrypted_gemini_key,
                updated_at = excluded.updated_at
        ''', (user_id, encrypted, datetime.now()))
        conn.commit()
        conn.close()
        return True

    def get_gemini_key(self, user_id: int) -> Optional[str]:
        """Retrieve and decrypt the user's personal Gemini API key, if set"""
        from crypto_utils import decrypt_value

        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT encrypted_gemini_key FROM user_settings WHERE user_id = ?',
                       (user_id,))
        row = cursor.fetchone()
        conn.close()

        if not row or not row['encrypted_gemini_key']:
            return None

        try:
            return decrypt_value(row['encrypted_gemini_key'])
        except Exception:
            return None

    def has_gemini_key(self, user_id: int) -> bool:
        return self.get_gemini_key(user_id) is not None

    def delete_gemini_key(self, user_id: int) -> bool:
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM user_settings WHERE user_id = ?', (user_id,))
        conn.commit()
        conn.close()
        return True
