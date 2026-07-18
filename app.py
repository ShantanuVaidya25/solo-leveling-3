"""
Solo Leveling Fitness - Flask Backend API (IMPROVED)
Fixed quest generation with better error handling
"""

from flask import Flask, request, jsonify, session, render_template
from flask_cors import CORS
from datetime import datetime, timedelta
from functools import wraps
from werkzeug.utils import secure_filename
import json
import os
import sys
import uuid
import traceback

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from models import Database, User, PlayerStats, ExerciseManager, WeeklyPlanManager, UserSettings
from quest_generator import AIQuestGenerator
from physique_analyzer import PhysiqueAnalyzer

app = Flask(__name__, 
            template_folder='../templates',
            static_folder='../static')
app.secret_key = 'your-secret-key-change-in-production-2025'
CORS(app, supports_credentials=True)

# Initialize database
db = Database()
user_manager = User(db)
stats_manager = PlayerStats(db)
exercise_manager = ExerciseManager(db)
quest_generator = AIQuestGenerator(db)
weekly_plan_manager = WeeklyPlanManager(db)
user_settings = UserSettings(db)

# A server-wide fallback key is OPTIONAL. If the site owner sets
# GEMINI_API_KEY, users without their own key can still use the feature
# (owner absorbs the cost). If not set, each user MUST provide their own
# key via Settings before the "Become Like..." feature works for them.
_fallback_analyzer = PhysiqueAnalyzer()  # uses GEMINI_API_KEY env var if present


def get_analyzer_for_user(uid: int) -> PhysiqueAnalyzer:
    """
    Resolve which AI client to use for this user: their own personal key
    if they've set one in Settings, otherwise the server's shared key (if
    the site owner configured one), otherwise an unconfigured instance
    that will fail gracefully with a clear "add your key" message.
    """
    personal_key = user_settings.get_gemini_key(uid)
    if personal_key:
        return PhysiqueAnalyzer(api_key=personal_key)
    return _fallback_analyzer

# Upload folder for physique reference photos
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}


def allowed_image(filename: str) -> bool:
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS


# Authentication decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Authentication required'}), 401
        return f(*args, **kwargs)
    return decorated_function


# ============================================================================
# AUTHENTICATION ENDPOINTS
# ============================================================================

@app.route('/')
def index():
    """Serve main application page"""
    return render_template('index.html')


@app.route('/api/register', methods=['POST'])
def register():
    """Register a new user"""
    data = request.json
    
    username = data.get('username')
    email = data.get('email')
    password = data.get('password')
    
    if not all([username, email, password]):
        return jsonify({'error': 'Missing required fields'}), 400
    
    user_id = user_manager.create_user(username, email, password)
    
    if user_id:
        print(f"✅ New user registered: {username} (ID: {user_id})")
        return jsonify({
            'success': True,
            'message': 'Account created successfully!',
            'user_id': user_id
        }), 201
    else:
        return jsonify({'error': 'Username or email already exists'}), 409


@app.route('/api/login', methods=['POST'])
def login():
    """Authenticate user"""
    data = request.json
    
    username = data.get('username')
    password = data.get('password')
    
    user = user_manager.authenticate(username, password)
    
    if user:
        session['user_id'] = user['id']
        session['username'] = user['username']
        
        # Get player stats
        stats = stats_manager.get_player_stats(user['id'])
        
        print(f"✅ User logged in: {username} (Has stats: {stats is not None})")
        
        return jsonify({
            'success': True,
            'message': 'Welcome back, Hunter!',
            'user': {
                'id': user['id'],
                'username': user['username'],
                'has_stats': stats is not None
            }
        })
    else:
        return jsonify({'error': 'Invalid credentials'}), 401


@app.route('/api/logout', methods=['POST'])
def logout():
    """Logout user"""
    username = session.get('username', 'Unknown')
    session.clear()
    print(f"👋 User logged out: {username}")
    return jsonify({'success': True, 'message': 'Logged out successfully'})


@app.route('/api/check-auth', methods=['GET'])
def check_auth():
    """Check if user is authenticated"""
    if 'user_id' in session:
        user = user_manager.get_user_by_id(session['user_id'])
        stats = stats_manager.get_player_stats(session['user_id'])
        
        return jsonify({
            'authenticated': True,
            'user': {
                'id': user['id'],
                'username': user['username'],
                'has_stats': stats is not None
            }
        })
    else:
        return jsonify({'authenticated': False})


# ============================================================================
# PLAYER STATS ENDPOINTS
# ============================================================================

@app.route('/api/setup-profile', methods=['POST'])
@login_required
def setup_profile():
    """Setup initial player profile"""
    data = request.json
    user_id = session['user_id']
    
    # Get body information
    age = data.get('age')
    height_cm = data.get('height_cm')
    weight_kg = data.get('weight_kg')
    target_height = data.get('target_height')
    target_weight = data.get('target_weight')
    
    # Multi-select "Primary Objective Path" goals + related preferences
    primary_focus_areas = data.get('primary_focus_areas', [])
    experience_level = data.get('experience_level', 'beginner')
    days_per_week = data.get('days_per_week', 5)
    
    if not all([age, height_cm, weight_kg]):
        return jsonify({'error': 'Missing required fields'}), 400
    
    if not primary_focus_areas:
        return jsonify({'error': 'Please select at least one objective from your Primary Objective Path'}), 400
    
    # Create player stats
    success = stats_manager.create_player_stats(
        user_id, age, height_cm, weight_kg,
        target_height, target_weight,
        primary_focus_areas, experience_level, days_per_week
    )
    
    if not success:
        return jsonify({'error': 'Profile already exists'}), 409
    
    # Add initial exercises if provided
    initial_exercises = data.get('initial_exercises', [])
    for exercise in initial_exercises:
        exercise_manager.add_or_update_exercise(
            user_id,
            exercise['name'],
            exercise['category'],
            exercise.get('max_reps', 0),
            exercise.get('max_weight', 0),
            exercise.get('max_duration', 0)
        )
    
    # Also persist each selected objective as a tracked goal so it shows
    # up in the Goals tab and factors into long-term progress tracking
    conn = db.get_connection()
    cursor = conn.cursor()
    goal_labels = {
        'strength': 'Build Strength',
        'muscle_gain': 'Gain Muscle',
        'weight_loss': 'Lose Weight',
        'endurance': 'Improve Endurance & Stamina',
        'flexibility': 'Improve Flexibility & Mobility',
        'height_growth': 'Support Height Growth',
        'general_fitness': 'General Fitness & Health',
        'athletic_performance': 'Sport-Specific Athletic Performance'
    }
    for path in primary_focus_areas:
        cursor.execute('''
            INSERT INTO goals (user_id, goal_type, goal_name, target_value, priority)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, path, goal_labels.get(path, path.replace('_', ' ').title()),
              100, 'high'))
    conn.commit()
    conn.close()
    
    # Immediately generate today's quest using the selected objectives so the
    # user has a workout plan waiting the moment setup finishes
    try:
        quest = quest_generator.generate_daily_quest(user_id, [], primary_focus_areas)
        quest_generator.save_daily_quest(user_id, quest)
    except Exception as e:
        print(f"⚠️  Could not pre-generate first quest: {e}")
    
    print(f"✅ Profile created for user {user_id}")
    print(f"   Age: {age}, Height: {height_cm}cm, Weight: {weight_kg}kg")
    print(f"   Objective path: {primary_focus_areas}")
    print(f"   Initial exercises: {len(initial_exercises)}")
    
    return jsonify({
        'success': True,
        'message': 'Profile created! Your journey begins now, Hunter!'
    })


@app.route('/api/stats', methods=['GET'])
@login_required
def get_stats():
    """Get player stats"""
    user_id = session['user_id']
    stats = stats_manager.get_player_stats(user_id)
    
    if not stats:
        return jsonify({'error': 'Stats not found'}), 404
    
    return jsonify({'stats': stats})


@app.route('/api/stats/allocate', methods=['POST'])
@login_required
def allocate_stats():
    """Allocate stat points"""
    data = request.json
    user_id = session['user_id']
    
    success = stats_manager.allocate_stat_points(
        user_id,
        data.get('strength', 0),
        data.get('endurance', 0),
        data.get('agility', 0),
        data.get('vitality', 0)
    )
    
    if success:
        stats = stats_manager.get_player_stats(user_id)
        return jsonify({
            'success': True,
            'message': 'Stats allocated successfully!',
            'stats': stats
        })
    else:
        return jsonify({'error': 'Invalid stat allocation'}), 400


@app.route('/api/stats/update-measurements', methods=['POST'])
@login_required
def update_measurements():
    """Update body measurements"""
    data = request.json
    user_id = session['user_id']
    
    success = stats_manager.update_body_measurements(
        user_id,
        data.get('height_cm'),
        data.get('weight_kg')
    )
    
    if success:
        stats = stats_manager.get_player_stats(user_id)
        return jsonify({
            'success': True,
            'message': 'Measurements updated!',
            'stats': stats
        })
    else:
        return jsonify({'error': 'Update failed'}), 400


# ============================================================================
# QUEST ENDPOINTS (IMPROVED)
# ============================================================================

@app.route('/api/quest/today', methods=['GET'])
@login_required
def get_todays_quest():
    """Get or generate today's quest"""
    user_id = session['user_id']
    username = session.get('username', 'Unknown')
    
    try:
        print(f"\n{'='*60}")
        print(f"📋 Quest request from: {username} (ID: {user_id})")
        
        # Check if user has stats
        stats = stats_manager.get_player_stats(user_id)
        if not stats:
            print(f"❌ User {user_id} has no stats - needs profile setup")
            return jsonify({
                'error': 'Please complete profile setup first',
                'needs_setup': True
            }), 400
        
        print(f"✅ User stats found - Level {stats['level']}")
        
        # Check if quest already exists for today
        quest = quest_generator.get_todays_quest(user_id)
        
        if quest:
            print(f"✅ Existing quest found for today")
            print(f"   Title: {quest['title']}")
            print(f"   Exercises: {len(quest['exercises'])}")
            print(f"   Completed: {quest.get('completed', False)}")
        else:
            print(f"🔄 No quest for today - generating new quest...")
            
            # Get user goals
            conn = db.get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM goals 
                WHERE user_id = ? AND status = 'active'
            ''', (user_id,))
            goals = [dict(row) for row in cursor.fetchall()]
            conn.close()
            
            print(f"   Active goals: {len(goals)}")
            for goal in goals:
                print(f"     - {goal['goal_type']}: {goal['goal_name']}")
            
            primary_focus_areas = stats_manager.get_primary_focus_areas(user_id)
            print(f"   Primary objective path: {primary_focus_areas}")
            
            # Generate new quest
            try:
                quest = quest_generator.generate_daily_quest(user_id, goals, primary_focus_areas)
                print(f"✅ Quest generated successfully!")
                print(f"   Title: {quest['title']}")
                print(f"   Exercises: {len(quest['exercises'])}")
                print(f"   Difficulty: {quest['difficulty']}")
                print(f"   EXP Reward: {quest['exp_reward']}")
                
                # Save quest
                quest_id = quest_generator.save_daily_quest(user_id, quest)
                quest['id'] = quest_id
                print(f"   Quest ID: {quest_id}")
                
                # Print exercise details
                for i, ex in enumerate(quest['exercises'], 1):
                    print(f"   {i}. {ex['name']}: {ex.get('sets', 1)} sets")
                
            except Exception as e:
                print(f"❌ ERROR generating quest: {e}")
                traceback.print_exc()
                return jsonify({
                    'error': f'Failed to generate quest: {str(e)}'
                }), 500
        
        print(f"{'='*60}\n")
        return jsonify({'quest': quest})
        
    except Exception as e:
        print(f"❌ CRITICAL ERROR in get_todays_quest: {e}")
        traceback.print_exc()
        return jsonify({
            'error': 'Server error while fetching quest',
            'details': str(e)
        }), 500


@app.route('/api/quest/complete', methods=['POST'])
@login_required
def complete_quest():
    """Complete a quest"""
    data = request.json
    user_id = session['user_id']
    username = session.get('username', 'Unknown')
    
    quest_id = data.get('quest_id')
    completions = data.get('completions', [])
    
    print(f"\n🎯 Quest completion from {username}")
    print(f"   Quest ID: {quest_id}")
    print(f"   Exercises completed: {len(completions)}")
    
    try:
        result = quest_generator.complete_quest(user_id, quest_id, completions)
        
        if result.get('success'):
            print(f"✅ Quest completed!")
            print(f"   EXP gained: {result['exp_gained']}")
            if result['level_result'].get('leveled_up'):
                print(f"   🎉 LEVEL UP! New level: {result['level_result']['new_level']}")
        
        return jsonify(result)
        
    except Exception as e:
        print(f"❌ Error completing quest: {e}")
        traceback.print_exc()
        return jsonify({
            'error': 'Failed to complete quest',
            'details': str(e)
        }), 500


@app.route('/api/quest/history', methods=['GET'])
@login_required
def get_quest_history():
    """Get quest completion history"""
    user_id = session['user_id']
    days = request.args.get('days', 30, type=int)
    
    conn = db.get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT * FROM daily_quests
        WHERE user_id = ? 
        AND quest_date >= date('now', ? || ' days')
        ORDER BY quest_date DESC
    ''', (user_id, -days))
    
    quests = []
    for row in cursor.fetchall():
        quest_data = json.loads(row['quest_data'])
        quest_data['id'] = row['id']
        quest_data['completed'] = bool(row['completed'])
        quest_data['completed_at'] = row['completed_at']
        quests.append(quest_data)
    
    conn.close()
    
    return jsonify({'quests': quests})


# ============================================================================
# EXERCISE ENDPOINTS
# ============================================================================

@app.route('/api/exercises', methods=['GET'])
@login_required
def get_exercises():
    """Get all user exercises"""
    user_id = session['user_id']
    exercises = exercise_manager.get_user_exercises(user_id)
    
    return jsonify({'exercises': exercises})


@app.route('/api/exercises/add', methods=['POST'])
@login_required
def add_exercise():
    """Add or update exercise record"""
    data = request.json
    user_id = session['user_id']
    
    success = exercise_manager.add_or_update_exercise(
        user_id,
        data.get('name'),
        data.get('category'),
        data.get('max_reps', 0),
        data.get('max_weight', 0),
        data.get('max_duration', 0)
    )
    
    if success:
        return jsonify({
            'success': True,
            'message': 'Exercise record updated!'
        })
    else:
        return jsonify({'error': 'Failed to update exercise'}), 400


# ============================================================================
# GOALS ENDPOINTS
# ============================================================================

@app.route('/api/goals', methods=['GET'])
@login_required
def get_goals():
    """Get all user goals"""
    user_id = session['user_id']
    
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT * FROM goals 
        WHERE user_id = ?
        ORDER BY 
            CASE status 
                WHEN 'active' THEN 1 
                WHEN 'completed' THEN 2 
                ELSE 3 
            END,
            priority DESC
    ''', (user_id,))
    
    goals = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return jsonify({'goals': goals})


@app.route('/api/goals/add', methods=['POST'])
@login_required
def add_goal():
    """Add a new goal"""
    data = request.json
    user_id = session['user_id']
    
    conn = db.get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO goals 
        (user_id, goal_type, goal_name, target_value, current_value, 
         deadline, priority)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (user_id, data.get('goal_type'), data.get('goal_name'),
          data.get('target_value'), data.get('current_value', 0),
          data.get('deadline'), data.get('priority', 'medium')))
    
    conn.commit()
    goal_id = cursor.lastrowid
    conn.close()
    
    print(f"✅ Goal added for user {user_id}: {data.get('goal_name')}")
    
    return jsonify({
        'success': True,
        'message': 'Goal added!',
        'goal_id': goal_id
    })


@app.route('/api/goals/<int:goal_id>/update', methods=['POST'])
@login_required
def update_goal(goal_id):
    """Update goal progress"""
    data = request.json
    user_id = session['user_id']
    
    conn = db.get_connection()
    cursor = conn.cursor()
    
    updates = []
    params = []
    
    if 'current_value' in data:
        updates.append('current_value = ?')
        params.append(data['current_value'])
    
    if 'status' in data:
        updates.append('status = ?')
        params.append(data['status'])
        if data['status'] == 'completed':
            updates.append('completed_at = ?')
            params.append(datetime.now())
    
    params.extend([user_id, goal_id])
    
    cursor.execute(f'''
        UPDATE goals 
        SET {', '.join(updates)}
        WHERE user_id = ? AND id = ?
    ''', params)
    
    conn.commit()
    conn.close()
    
    return jsonify({'success': True, 'message': 'Goal updated!'})


@app.route('/api/goals/objective-path', methods=['POST'])
@login_required
def update_objective_path():
    """Update the multi-select Primary Objective Path after initial setup"""
    data = request.json
    user_id = session['user_id']
    focus_areas = data.get('primary_focus_areas', [])
    
    if not focus_areas:
        return jsonify({'error': 'Select at least one objective'}), 400
    
    stats_manager.update_primary_focus_areas(user_id, focus_areas)
    
    return jsonify({
        'success': True,
        'message': 'Objective path updated! Tomorrow\'s quest will reflect your new focus.'
    })


# ============================================================================
# PHYSIQUE ANALYZER ENDPOINTS
# ("Become Like X" - AI Quest Log Generator)
# ============================================================================

@app.route('/api/physique/status', methods=['GET'])
@login_required
def physique_status():
    """Check whether AI physique analysis is configured for THIS user"""
    user_id = session['user_id']
    analyzer = get_analyzer_for_user(user_id)
    return jsonify({
        'configured': analyzer.is_configured(),
        'using_personal_key': user_settings.has_gemini_key(user_id),
        'shared_key_available': _fallback_analyzer.is_configured()
    })


@app.route('/api/physique/analyze', methods=['POST'])
@login_required
def analyze_physique():
    """
    Generate a Quest Log by analyzing either:
    - A named character/person (form field 'target_name'), OR
    - An uploaded reference photo (multipart file field 'image')
    
    Uses the requesting user's personal API key if they've set one in
    Settings, otherwise falls back to the server's shared key if the site
    owner configured one.
    """
    user_id = session['user_id']
    username = session.get('username', 'Unknown')
    analyzer = get_analyzer_for_user(user_id)
    
    target_name = request.form.get('target_name', '').strip() or None
    image_file = request.files.get('image')
    image_path = None
    saved_filename = None
    
    print(f"\n🎭 Physique analysis request from {username}")
    print(f"   Target name: {target_name}")
    print(f"   Image uploaded: {image_file is not None and image_file.filename}")
    print(f"   Using personal key: {user_settings.has_gemini_key(user_id)}")
    
    if image_file and image_file.filename:
        if not allowed_image(image_file.filename):
            return jsonify({'error': 'Unsupported image type. Use JPG, PNG, or WEBP.'}), 400
        
        ext = image_file.filename.rsplit('.', 1)[1].lower()
        saved_filename = f"{user_id}_{uuid.uuid4().hex}.{ext}"
        image_path = os.path.join(UPLOAD_FOLDER, saved_filename)
        image_file.save(image_path)
    
    if not target_name and not image_path:
        return jsonify({'error': 'Provide a character/person name or upload a photo.'}), 400
    
    try:
        result = analyzer.generate_quest_log(
            target_name=target_name,
            image_path=image_path
        )
        
        if not result.get('success'):
            print(f"❌ Physique analysis failed: {result.get('error')}")
            return jsonify(result), 400 if result.get('setup_required') else 500
        
        # Save to database
        conn = db.get_connection()
        cursor = conn.cursor()
        
        # Deactivate previous active quest logs (only one "current build goal" at a time)
        cursor.execute('UPDATE physique_quests SET is_active = 0 WHERE user_id = ?', (user_id,))
        
        cursor.execute('''
            INSERT INTO physique_quests 
            (user_id, target_name, source_type, image_path, quest_log_markdown, is_active)
            VALUES (?, ?, ?, ?, ?, 1)
        ''', (user_id, result['target_name'], result['source_type'],
              saved_filename, result['quest_log_markdown']))
        
        physique_quest_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        result['id'] = physique_quest_id
        print(f"✅ Quest Log generated and saved (ID: {physique_quest_id})")
        
        # Convert the weekly split into structured data so it drives the
        # actual daily quests, not just a wall of text the user reads once.
        weekly_result = analyzer.extract_structured_weekly_plan(result['quest_log_markdown'])
        if weekly_result.get('success'):
            weekly_plan_manager.save_weekly_plan(user_id, physique_quest_id, weekly_result['days'])
            result['weekly_plan_linked'] = True
            print(f"✅ Weekly plan structured and linked to daily quests")
        else:
            result['weekly_plan_linked'] = False
            result['weekly_plan_error'] = weekly_result.get('error')
            print(f"⚠️  Weekly plan structuring failed: {weekly_result.get('error')}")
        
        return jsonify(result)
        
    except Exception as e:
        print(f"❌ Error in physique analysis: {e}")
        traceback.print_exc()
        return jsonify({'error': f'Analysis failed: {str(e)}'}), 500


@app.route('/api/physique/history', methods=['GET'])
@login_required
def physique_history():
    """Get past physique analysis Quest Logs for this user"""
    user_id = session['user_id']
    
    conn = db.get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, target_name, source_type, image_path, quest_log_markdown, 
               is_active, created_at
        FROM physique_quests
        WHERE user_id = ?
        ORDER BY created_at DESC
    ''', (user_id,))
    
    history = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return jsonify({'history': history})


@app.route('/api/physique/<int:quest_log_id>/activate', methods=['POST'])
@login_required
def activate_physique_quest(quest_log_id):
    """Mark a past Quest Log as the active build goal and re-link its weekly plan"""
    user_id = session['user_id']
    
    conn = db.get_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT id, quest_log_markdown FROM physique_quests WHERE id = ? AND user_id = ?',
                   (quest_log_id, user_id))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return jsonify({'error': 'Quest Log not found'}), 404
    
    quest_log_markdown = row['quest_log_markdown']
    
    cursor.execute('UPDATE physique_quests SET is_active = 0 WHERE user_id = ?', (user_id,))
    cursor.execute('UPDATE physique_quests SET is_active = 1 WHERE id = ?', (quest_log_id,))
    conn.commit()
    conn.close()
    
    # Re-derive the structured weekly plan for the newly-activated goal so
    # daily quests immediately reflect it instead of the previous one.
    analyzer = get_analyzer_for_user(user_id)
    weekly_result = analyzer.extract_structured_weekly_plan(quest_log_markdown)
    if weekly_result.get('success'):
        weekly_plan_manager.save_weekly_plan(user_id, quest_log_id, weekly_result['days'])
    
    return jsonify({'success': True, 'message': 'Build goal activated!'})


@app.route('/api/physique/<int:quest_log_id>', methods=['DELETE'])
@login_required
def delete_physique_quest(quest_log_id):
    """Delete a saved physique Quest Log"""
    user_id = session['user_id']
    
    conn = db.get_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT image_path, is_active FROM physique_quests WHERE id = ? AND user_id = ?',
                   (quest_log_id, user_id))
    row = cursor.fetchone()
    
    if not row:
        conn.close()
        return jsonify({'error': 'Quest Log not found'}), 404
    
    was_active = bool(row['is_active'])
    
    if row['image_path']:
        img_path = os.path.join(UPLOAD_FOLDER, row['image_path'])
        if os.path.exists(img_path):
            os.remove(img_path)
    
    cursor.execute('DELETE FROM physique_quests WHERE id = ? AND user_id = ?',
                   (quest_log_id, user_id))
    conn.commit()
    conn.close()
    
    # If the deleted goal was the active one, clear its weekly plan too --
    # daily quests fall back to the normal algorithmic generator.
    if was_active:
        weekly_plan_manager.clear_plan(user_id)
    
    return jsonify({'success': True, 'message': 'Quest Log deleted'})


# ============================================================================
# USER SETTINGS ENDPOINTS
# (personal AI API keys, for when this app is deployed for multiple people)
# ============================================================================

@app.route('/api/settings/api-key', methods=['GET'])
@login_required
def get_api_key_status():
    """Check whether the current user has a personal key saved (never returns the key itself)"""
    user_id = session['user_id']
    return jsonify({
        'has_personal_key': user_settings.has_gemini_key(user_id),
        'shared_key_available': _fallback_analyzer.is_configured()
    })


@app.route('/api/settings/api-key', methods=['POST'])
@login_required
def save_api_key():
    """Save (or replace) the current user's personal Gemini API key, encrypted at rest"""
    from crypto_utils import is_configured as encryption_is_configured
    
    if not encryption_is_configured():
        return jsonify({
            'error': (
                'Server-side encryption is not configured. An administrator needs to '
                'set the APP_ENCRYPTION_KEY environment variable before personal API '
                'keys can be safely stored. See README for setup instructions.'
            )
        }), 503
    
    data = request.json
    api_key = (data.get('api_key') or '').strip()
    
    if not api_key:
        return jsonify({'error': 'API key cannot be empty'}), 400
    
    if len(api_key) < 10:
        return jsonify({'error': 'That doesn\'t look like a valid API key'}), 400
    
    user_id = session['user_id']
    
    # Do a lightweight live check that the key actually works before saving it,
    # so users get immediate feedback instead of a silent failure later.
    test_analyzer = PhysiqueAnalyzer(api_key=api_key)
    if not test_analyzer.is_configured():
        return jsonify({'error': 'Could not initialize with that key. Double-check it\'s correct.'}), 400
    
    user_settings.save_gemini_key(user_id, api_key)
    
    print(f"✅ User {session.get('username')} saved a personal Gemini API key")
    
    return jsonify({
        'success': True,
        'message': 'Your API key has been saved securely. It will be used for your AI features going forward.'
    })


@app.route('/api/settings/api-key', methods=['DELETE'])
@login_required
def delete_api_key():
    """Remove the current user's personal API key (falls back to shared key if available)"""
    user_id = session['user_id']
    user_settings.delete_gemini_key(user_id)
    
    return jsonify({
        'success': True,
        'message': 'Personal API key removed.'
    })


# ============================================================================
# SOCIAL / FRIENDS ENDPOINTS
# ============================================================================

@app.route('/api/friends', methods=['GET'])
@login_required
def get_friends():
    """Get user's friends list"""
    user_id = session['user_id']
    
    conn = db.get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT u.id, u.username, ps.level, ps.exp, f.status
        FROM friends f
        JOIN users u ON (f.friend_id = u.id)
        LEFT JOIN player_stats ps ON (u.id = ps.user_id)
        WHERE f.user_id = ? AND f.status = 'accepted'
        ORDER BY ps.level DESC
    ''', (user_id,))
    
    friends = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return jsonify({'friends': friends})


@app.route('/api/friends/search', methods=['GET'])
@login_required
def search_users():
    """Search for users to add as friends"""
    query = request.args.get('q', '')
    user_id = session['user_id']
    
    if len(query) < 2:
        return jsonify({'users': []})
    
    conn = db.get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT u.id, u.username, ps.level
        FROM users u
        LEFT JOIN player_stats ps ON (u.id = ps.user_id)
        WHERE u.username LIKE ? AND u.id != ?
        LIMIT 20
    ''', (f'%{query}%', user_id))
    
    users = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return jsonify({'users': users})


@app.route('/api/friends/add', methods=['POST'])
@login_required
def add_friend():
    """Send friend request"""
    data = request.json
    user_id = session['user_id']
    friend_id = data.get('friend_id')
    
    conn = db.get_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            INSERT INTO friends (user_id, friend_id, status)
            VALUES (?, ?, 'pending')
        ''', (user_id, friend_id))
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'message': 'Friend request sent!'})
    except:
        conn.close()
        return jsonify({'error': 'Friend request already exists'}), 409


@app.route('/api/friends/accept', methods=['POST'])
@login_required
def accept_friend():
    """Accept friend request"""
    data = request.json
    user_id = session['user_id']
    friend_id = data.get('friend_id')
    
    conn = db.get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        UPDATE friends
        SET status = 'accepted', accepted_at = ?
        WHERE user_id = ? AND friend_id = ?
    ''', (datetime.now(), friend_id, user_id))
    
    # Create reciprocal friendship
    cursor.execute('''
        INSERT OR IGNORE INTO friends (user_id, friend_id, status, accepted_at)
        VALUES (?, ?, 'accepted', ?)
    ''', (user_id, friend_id, datetime.now()))
    
    conn.commit()
    conn.close()
    
    return jsonify({'success': True, 'message': 'Friend added!'})


@app.route('/api/leaderboard', methods=['GET'])
@login_required
def get_leaderboard():
    """Get global or friends leaderboard"""
    user_id = session['user_id']
    scope = request.args.get('scope', 'global')
    
    conn = db.get_connection()
    cursor = conn.cursor()
    
    if scope == 'friends':
        cursor.execute('''
            SELECT u.id, u.username, ps.level, ps.exp, ps.strength, 
                   ps.endurance, ps.agility, ps.vitality
            FROM player_stats ps
            JOIN users u ON (ps.user_id = u.id)
            WHERE ps.user_id IN (
                SELECT friend_id FROM friends 
                WHERE user_id = ? AND status = 'accepted'
            ) OR ps.user_id = ?
            ORDER BY ps.level DESC, ps.exp DESC
            LIMIT 50
        ''', (user_id, user_id))
    else:
        cursor.execute('''
            SELECT u.id, u.username, ps.level, ps.exp, ps.strength,
                   ps.endurance, ps.agility, ps.vitality
            FROM player_stats ps
            JOIN users u ON (ps.user_id = u.id)
            ORDER BY ps.level DESC, ps.exp DESC
            LIMIT 100
        ''', ())
    
    leaderboard = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return jsonify({'leaderboard': leaderboard})


# ============================================================================
# STATISTICS ENDPOINTS
# ============================================================================

@app.route('/api/stats/progress', methods=['GET'])
@login_required
def get_progress_data():
    """Get progress data for charts"""
    user_id = session['user_id']
    days = request.args.get('days', 30, type=int)
    
    conn = db.get_connection()
    cursor = conn.cursor()
    
    # Get daily EXP gains
    cursor.execute('''
        SELECT quest_date as date, SUM(exp_reward) as exp
        FROM daily_quests
        WHERE user_id = ? 
        AND quest_date >= date('now', ? || ' days')
        AND completed = 1
        GROUP BY quest_date
        ORDER BY quest_date
    ''', (user_id, -days))
    
    exp_data = [dict(row) for row in cursor.fetchall()]
    
    # Get workout completions
    cursor.execute('''
        SELECT quest_date as date, COUNT(*) as workouts
        FROM daily_quests
        WHERE user_id = ?
        AND quest_date >= date('now', ? || ' days')
        AND completed = 1
        GROUP BY quest_date
        ORDER BY quest_date
    ''', (user_id, -days))
    
    workout_data = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    
    return jsonify({
        'exp_progress': exp_data,
        'workout_completions': workout_data
    })


if __name__ == '__main__':
    print("\n" + "="*60)
    print("⚔️  SOLO LEVELING FITNESS SYSTEM")
    print("="*60)
    print("\n🚀 Server starting...")
    print(f"📍 Access at: http://localhost:5000")
    print(f"📊 Database: {db.db_path}")
    print("\n💡 Tip: Check this terminal for quest generation logs")
    print("\n" + "="*60 + "\n")
    
    app.run(debug=True, host='0.0.0.0', port=5000)
