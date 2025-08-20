import os
import json
import random
import shutil
import time
import google.generativeai as genai
import dotenv
from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from datetime import timedelta
from google.api_core import exceptions

dotenv.load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-2.5-flash")
GEMINI_CACHE_DIR = 'gemini_cache'

topic_prompts = {}
chat_sessions = {}

SYSTEM_PROMPTS_PATH = os.path.join('prompts/general_system_prompts.json')

try:
    with open(SYSTEM_PROMPTS_PATH, 'r', encoding='utf-8') as f:
        prompts_data = json.load(f)
    print("Prompt dosyası başarıyla yüklendi.")
except Exception as e:
    print(f"HATA: Prompt dosyası ({SYSTEM_PROMPTS_PATH}) yüklenemedi: {e}")
    prompts_data = {}

LISTS_DIR = 'lists/user_lists'
MAIN_LISTS_DIR = 'lists/main_lists'


def list_object_translate(prompt_content):
    with open(SYSTEM_PROMPTS_PATH, 'r', encoding='utf-8') as dosya:
        prompt_data = json.load(dosya)

    prompt_sablonu = prompt_data.get("translate_prompt")

    prompt_for_translation = prompt_sablonu.replace("{prompt_text}", prompt_content)

    response = model.generate_content(prompt_for_translation)
    time.sleep(2)
    return response.text.strip()


def generate_question(prompt_icerik, konu, level='B1'):
    print(f"--- 'generate_question' fonksiyonu '{prompt_icerik}' için çalıştırıldı. ---")
    promptpath = "prompts/general_system_prompts.json"

    try:
        with open(promptpath, 'r', encoding='utf-8') as dosya:
            prompts_data = json.load(dosya)

        prompt_sablonu = prompts_data.get("quiz_sentence_completion_prompt")
        if not prompt_sablonu:
            print("HATA: 'quiz_sentence_completion_prompt' anahtarı JSON'da bulunamadı!")
            return {"error": "'quiz_sentence_completion_prompt' JSON'da bulunamadı."}

        final_prompt = prompt_sablonu.replace("{konu}", konu) \
            .replace("{level}", level) \
            .replace("{prompt_text}", prompt_icerik)

        print("--> Gemini'ye gönderilecek prompt hazırlandı. API çağrısı yapılıyor...")
        response = model.generate_content(final_prompt)
        time.sleep(1)

        print(f"--> Gemini'den gelen ham yanıt alindi: {response.text[:100]}...")
        cleaned_response_text = response.text.strip().replace('```json', '').replace('```', '')

        parsed_json = json.loads(cleaned_response_text)
        print("--> Gemini yanıtı başarıyla JSON olarak ayrıştırıldı.")
        return parsed_json

    except Exception as e:
        print(f"!!! 'generate_question' İÇİNDE KRİTİK HATA: {e} !!!")
        return {"error": f"generate_question içinde beklenmedik hata: {str(e)}"}


def is_likely_english(text):
    try:
        return all(ord(c) < 128 for c in text)
    except TypeError:
        return False


def generateJSON(jName):
    os.makedirs(LISTS_DIR, exist_ok=True)
    full_path = os.path.join(LISTS_DIR, f"{jName}.json")
    if not os.path.exists(full_path):
        with open(full_path, "w", encoding="utf-8") as f:
            json.dump({}, f, indent=4)


def load_list_data(list_name, directory=LISTS_DIR):
    full_path = os.path.join(directory, f"{list_name}.json")
    if os.path.exists(full_path):
        with open(full_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_list_data(list_name, data, directory=LISTS_DIR):
    full_path = os.path.join(directory, f"{list_name}.json")
    os.makedirs(directory, exist_ok=True)
    with open(full_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)


def gemini_chat_response(user_message, topic_id):
    prompt_template = prompts_data.get(topic_id)
    if not prompt_template:
        print(f"HATA: teacher_prompts.json dosyasında '{topic_id}' için prompt bulunamadı.")
        return "Üzgünüm, bu konu hakkında şu anda sana yardımcı olamıyorum."

    final_prompt = prompt_template.replace("{user_message}", user_message)

    try:
        response = model.generate_content(final_prompt)
        return response.text.strip()
    except Exception as e:
        print(f"Gemini AI Teacher hatası: {e}")
        return f"Yapay zekadan yanıt alınırken bir hata oluştu: {e}"


def ensure_english(text):
    prompt_template = prompts_data.get("ensure_english_prompt")

    if not prompt_template:
        print("HATA: 'ensure_english_prompt' anahtarı JSON dosyasında bulunamadı.")
        return text

    final_prompt = prompt_template.replace("{text_to_clean}", text)

    try:
        response = model.generate_content(final_prompt)
        return response.text.strip()
    except Exception as e:
        print(f"ensure_english hatası: {e}")
        return text


def gemini_smart_translate(text_to_translate, target_level, is_academic):
    if is_academic:
        prompt_key = "smart_translate_academic_prompt"
    else:
        prompt_key = "smart_translate_standard_prompt"

    prompt_template = prompts_data.get(prompt_key)

    if not prompt_template:
        error_message = f"HATA: '{prompt_key}' anahtarı JSON dosyasında bulunamadı."
        print(error_message)
        return error_message

    final_prompt = prompt_template.replace("{target_level}", target_level) \
        .replace("{text_to_translate}", text_to_translate)

    try:
        response = model.generate_content(final_prompt)
        return response.text.strip()
    except Exception as e:
        print(f"Akıllı Gemini çeviri hatası: {e}")
        return f"Çeviri sırasında bir hata oluştu: {e}"


app = Flask(__name__)
app.secret_key = 'buraya_guvenli_bir_anahtar_yazin'
app.permanent_session_lifetime = timedelta(days=1)


@app.route("/")
def home():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    return render_template("index.html")


@app.route("/aiagents/teacher")
def ai_chat():
    return render_template("teacher.html")


@app.route("/aiagents/generator")
def generator():
    return render_template("generator.html")


@app.route("/quiz")
def quiz():
    return render_template("quiz.html")


@app.route("/trainslate")
def trainslate():
    return render_template("Trainslate.html")


@app.route("/getLevelName", methods=["POST"])
def get_level():
    print(request.get_json())
    return jsonify({"level": 1})


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        data = request.get_json()
        username = data.get("username")
        password = data.get("password")

        if username == "admin" and password == "123456":
            session['logged_in'] = True
            return jsonify({"message": "Giriş başarılı"}), 200
        else:
            return jsonify({"message": "Kullanıcı adı veya şifre hatalı."}), 401
    return render_template("login.html")


@app.route("/logout", methods=["POST"])
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))


@app.route("/collection/<collection_name>")
def collection_detail(collection_name):
    if not session.get('logged_in'):
        return redirect(url_for('login'))

    is_main_list = False
    main_list_path = os.path.join(MAIN_LISTS_DIR, f"{collection_name}.json")
    if os.path.exists(main_list_path):
        is_main_list = True

    return render_template("collection_detail.html",
                           collection_name=collection_name,
                           is_main_list=is_main_list)


@app.route("/api/chat", methods=["POST"])
def chat_message():
    data = request.get_json()
    if not data:
        return jsonify({"status": "error", "message": "JSON veri bulunamadı."}), 400

    topic_id = data.get("topicId")
    user_message = data.get("message", "").strip()

    if not topic_id:
        return jsonify({"status": "error", "message": "Konu ID'si (topicId) eksik."}), 400

    if not user_message and topic_id in chat_sessions:
        print(f"'{topic_id}' için eski oturum temizleniyor ve yeni bir tane başlatılıyor...")
        del chat_sessions[topic_id]

    if topic_id not in chat_sessions:
        print(f"'{topic_id}' için YENİ sohbet oturumu başlatılıyor...")

        initial_prompt_text = prompts_data.get(topic_id)
        if not initial_prompt_text:
            print(f"HATA: '{topic_id}' anahtarı {SYSTEM_PROMPTS_PATH} dosyasında bulunamadı.")
            return jsonify({"status": "error", "message": "Bu konu için bir pratik başlatılamadı."}), 404

        if isinstance(initial_prompt_text, dict):
            prompt_object = initial_prompt_text
            role = prompt_object.get('role', 'İngilizce Öğretmeni.')
            persona = prompt_object.get('persona', 'Destekleyici ve profesyonel.')
            methodology = prompt_object.get('methodology', '')
            task = prompt_object.get('task', 'Konuyla ilgili pratik yap.')
            initial_prompt_text = f"ROLE: {role}\nPERSONA: {persona}\nMETHODOLOGY: {methodology}\nTASK: {task}"

        try:
            chat = model.start_chat(history=[
                {'role': 'user', 'parts': [initial_prompt_text]}
            ])
            chat_sessions[topic_id] = chat

        except Exception as e:
            print(f"Gemini chat başlatma hatası: {e}")
            return jsonify({"status": "error", "message": "Yapay zeka ile sohbet başlatılırken bir hata oluştu."}), 500

    chat = chat_sessions[topic_id]

    try:
        if not user_message:
            if len(chat.history) == 1:
                print(f"'{topic_id}' için dinamik başlangıç mesajı üretiliyor...")

                response = chat.send_message("Başla.")
                bot_response_text = response.text
            else:
                bot_response_text = chat.history[-1].parts[0].text
        else:
            response = chat.send_message(user_message)
            bot_response_text = response.text

        return jsonify({"status": "success", "botResponse": bot_response_text})

    except Exception as e:
        print(f"Gemini mesaj gönderme hatası: {e}")
        if topic_id in chat_sessions:
            del chat_sessions[topic_id]
        return jsonify({"status": "error", "message": "Yapay zekadan yanıt alınırken bir hata oluştu."}), 500


@app.route("/api/list-ekle", methods=["POST"])
def list_ekle():
    data = request.get_json()
    list_name = data.get("listName")

    if not list_name:
        return jsonify({"status": "error", "mesaj": "listName boş"}), 400

    safe_list_name = "".join(c for c in list_name if c.isalnum() or c in (' ', '-', '_')).strip()
    if not safe_list_name:
        return jsonify({"status": "error", "mesaj": "Geçersiz liste adı."}), 400

    full_path = os.path.join(LISTS_DIR, f"{safe_list_name}.json")
    if os.path.exists(full_path):
        return jsonify({"status": "error", "mesaj": "Bu isimde bir liste zaten var."}), 409

    generateJSON(safe_list_name)
    return jsonify({"status": "ok", "list": safe_list_name}), 200


@app.route('/api/get-collections', methods=['GET'])
def get_collections():
    collections = []
    try:
        if os.path.exists(LISTS_DIR):
            collections = [
                f[:-5] for f in os.listdir(LISTS_DIR)
                if f.endswith('.json') and os.path.isfile(os.path.join(LISTS_DIR, f))
            ]
    except Exception as e:
        print(f"Koleksiyonlar yüklenirken bir hata oluştu: {e}")
        return jsonify({"status": "error", "message": "Sunucu hatası: Koleksiyonlar yüklenemedi."}), 500

    return jsonify(collections)


@app.route('/api/get-main-lists', methods=['GET'])
def get_main_lists():
    if not os.path.exists(MAIN_LISTS_DIR):
        return jsonify([])

    main_lists = [
        f[:-5] for f in os.listdir(MAIN_LISTS_DIR)
        if f.endswith('.json') and os.path.isfile(os.path.join(MAIN_LISTS_DIR, f))
    ]
    return jsonify(main_lists)


@app.route('/api/copy-main-list', methods=['POST'])
def copy_main_list():
    data = request.get_json()
    list_name_to_copy = data.get("listName")

    if not list_name_to_copy:
        return jsonify({"status": "error", "message": "Kopyalanacak liste adı eksik."}), 400

    safe_list_name = "".join(c for c in list_name_to_copy if c.isalnum() or c in (' ', '-', '_')).strip()
    if not safe_list_name:
        return jsonify({"status": "error", "message": "Geçersiz liste adı."}), 400

    source_path = os.path.join(MAIN_LISTS_DIR, f"{safe_list_name}.json")
    destination_path = os.path.join(LISTS_DIR, f"{safe_list_name}.json")

    if not os.path.exists(source_path):
        return jsonify({"status": "error", "message": "Kaynak liste bulunamadı."}), 404

    if os.path.exists(destination_path):
        return jsonify({"status": "error", "message": "Bu liste zaten koleksiyonlarınızda var."}), 409

    try:
        os.makedirs(LISTS_DIR, exist_ok=True)
        shutil.copyfile(source_path, destination_path)
        return jsonify({"status": "ok", "message": f"'{safe_list_name}' koleksiyonlarınıza eklendi."}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": f"Liste kopyalanırken hata oluştu: {e}"}), 500


@app.route('/api/get-collection-words/<collection_name>', methods=['GET'])
def get_collection_words(collection_name):
    safe_collection_name = "".join(c for c in collection_name if c.isalnum() or c in (' ', '-', '_')).strip()
    if not safe_collection_name:
        return jsonify({"status": "error", "message": "Geçersiz koleksiyon adı."}), 400

    directory = MAIN_LISTS_DIR if os.path.exists(
        os.path.join(MAIN_LISTS_DIR, f"{safe_collection_name}.json")) else LISTS_DIR

    words_data = load_list_data(safe_collection_name, directory=directory)
    word_list = [{"original": k, "translation": v} for k, v in words_data.items()]
    return jsonify(word_list)


@app.route('/api/add-word-to-collection', methods=['POST'])
def add_word_to_collection():
    data = request.get_json()
    collection_name = data.get("collectionName")
    original_word = data.get("originalWord", "").strip()

    if not collection_name or not original_word:
        return jsonify({"status": "error", "message": "Koleksiyon adı veya kelime eksik."}), 400

    safe_collection_name = "".join(c for c in collection_name if c.isalnum() or c in (' ', '-', '_')).strip()
    if not safe_collection_name:
        return jsonify({"status": "error", "message": "Geçersiz koleksiyon adı."}), 400

    user_list_path = os.path.join(LISTS_DIR, f"{safe_collection_name}.json")
    if not os.path.exists(user_list_path):
        return jsonify({"status": "error",
                        "message": "Kelime eklemek için önce listeyi kopyalamanız veya oluşturmanız gerekir."}), 403

    translation = list_object_translate(original_word)

    if "hata oluştu" in translation.lower() or "içerik anlaşılmadı" in translation.lower():
        return jsonify(
            {"status": "error", "message": f"'{original_word}' kelimesi çevrilemedi veya anlaşılamadı."}), 400

    collection_data = load_list_data(safe_collection_name)
    collection_data[original_word] = translation
    save_list_data(safe_collection_name, collection_data)

    return jsonify({
        "status": "ok",
        "originalWord": original_word,
        "translation": translation,
        "collectionName": safe_collection_name
    })


@app.route('/api/delete-word-from-collection', methods=['POST'])
def delete_word_from_collection():
    data = request.get_json()
    collection_name = data.get("collectionName")
    word_to_delete = data.get("wordToDelete")

    if not collection_name or not word_to_delete:
        return jsonify({"status": "error", "message": "Koleksiyon adı veya silinecek kelime eksik."}), 400

    safe_collection_name = "".join(c for c in collection_name if c.isalnum() or c in (' ', '-', '_')).strip()
    if not safe_collection_name:
        return jsonify({"status": "error", "message": "Geçersiz koleksiyon adı."}), 400

    user_list_path = os.path.join(LISTS_DIR, f"{safe_collection_name}.json")
    if not os.path.exists(user_list_path):
        return jsonify({"status": "error", "message": "Hazır listelerden kelime silinemez."}), 403

    collection_data = load_list_data(safe_collection_name)

    if word_to_delete in collection_data:
        del collection_data[word_to_delete]
        save_list_data(safe_collection_name, collection_data)
        return jsonify({"status": "ok", "message": f"'{word_to_delete}' başarıyla silindi."}), 200
    else:
        return jsonify({"status": "error", "message": "Kelime bulunamadı."}), 404


@app.route('/api/delete-list', methods=['POST'])
def delete_list():
    data = request.get_json()
    list_name = data.get("listName")

    if not list_name:
        return jsonify({"status": "error", "message": "Liste adı eksik."}), 400

    safe_list_name = "".join(c for c in list_name if c.isalnum() or c in (' ', '-', '_')).strip()
    full_path = os.path.join(LISTS_DIR, f"{safe_list_name}.json")

    if not os.path.exists(full_path):
        return jsonify({"status": "error", "message": "Liste bulunamadı."}), 404

    if os.path.join(os.path.abspath(LISTS_DIR), os.path.basename(full_path)) != os.path.abspath(full_path):
        return jsonify({"status": "error", "message": "Geçersiz dosya yolu girişimi."}), 403

    try:
        os.remove(full_path)
        return jsonify({"status": "ok", "message": f"'{safe_list_name}' listesi başarıyla silindi."}), 200
    except OSError as e:
        return jsonify({"status": "error", "message": f"Dosya silinirken hata oluştu: {e}"}), 500


@app.route('/api/rename-list', methods=['POST'])
def rename_list():
    data = request.get_json()
    old_name = data.get("oldName")
    new_name = data.get("newName")

    if not old_name or not new_name:
        return jsonify({"status": "error", "message": "Eski veya yeni liste adı eksik."}), 400

    safe_old_name = "".join(c for c in old_name if c.isalnum() or c in (' ', '-', '_')).strip()
    safe_new_name = "".join(c for c in new_name if c.isalnum() or c in (' ', '-', '_')).strip()

    if not safe_new_name:
        return jsonify({"status": "error", "message": "Yeni liste adı boş olamaz."}), 400

    old_path = os.path.join(LISTS_DIR, f"{safe_old_name}.json")
    new_path = os.path.join(LISTS_DIR, f"{safe_new_name}.json")

    if not os.path.exists(old_path):
        return jsonify({"status": "error", "message": "Eski liste adı bulunamadı."}), 404

    if os.path.exists(new_path):
        return jsonify({"status": "error", "message": "Bu isimde bir liste zaten var."}), 409

    try:
        os.rename(old_path, new_path)
        return jsonify({"status": "ok", "message": f"Liste adı '{safe_old_name}' olarak değiştirildi."}), 200
    except OSError as e:
        return jsonify({"status": "error", "message": f"Dosya adı değiştirilirken hata oluştu: {e}"}), 500


@app.route('/api/get-all-quiz-lists', methods=['GET'])
def get_all_quiz_lists():
    all_lists = set()

    base_dir = 'lists'

    sub_dirs_to_scan = ['main_lists', 'user_lists']

    for sub_dir in sub_dirs_to_scan:

        current_path = os.path.join(base_dir, sub_dir)

        if os.path.isdir(current_path):
            try:

                for filename in os.listdir(current_path):
                    if filename.endswith('.json'):
                        list_name = filename[:-5]
                        all_lists.add(list_name)
            except Exception as e:

                print(f"'{current_path}' klasörü taranırken hata oluştu: {e}")

    return jsonify(sorted(list(all_lists)))


@app.route('/api/start-quiz', methods=['POST'])
def start_quiz():
    try:
        data = request.get_json()
        list_name = data.get('listName')
        question_type = data.get('questionType')
        difficulty_level = data.get('difficultyLevel', 'B1')

        file_path = os.path.join(LISTS_DIR, f"{list_name}.json")
        if not os.path.exists(file_path):
            file_path = os.path.join(MAIN_LISTS_DIR, f"{list_name}.json")

        if not os.path.exists(file_path):
            return jsonify({"status": "error", "message": f"'{list_name}' adında bir liste bulunamadı."}), 404

        with open(file_path, 'r', encoding='utf-8') as f:
            words_data = json.load(f)

        if len(words_data) < 3:
            return jsonify({"status": "error",
                            "message": "Bu listede quiz oluşturmak için yeterli (en az 3) içerik bulunmuyor."}), 400

        all_items = list(words_data.items())
        num_questions = min(10, len(all_items))
        quiz_items = random.sample(all_items, num_questions)

        quiz_questions = []
        error_log = []

        for content, translation in quiz_items:
            if question_type == 'sentence_completion':
                result = generate_question(prompt_icerik=content, konu=list_name, level=difficulty_level)

                if isinstance(result, dict) and 'error' not in result:

                    required_keys = ['question_sentence', 'correct_answer', 'distractor1', 'distractor2']
                    if all(key in result for key in required_keys):
                        options = [result['correct_answer'], result['distractor1'], result['distractor2']]
                        random.shuffle(options)
                        quiz_questions.append({
                            "question": result['question_sentence'],
                            "options": options,
                            "correct_answer": result['correct_answer']
                        })
                    else:

                        error_log.append(f"'{content}' için gelen yanıtta beklenen anahtarlar eksik.")
                else:
                    error_message = result.get('error', 'Bilinmeyen bir hata.')
                    error_log.append(f"'{content}' için soru üretilemedi: {error_message}")

            elif question_type == 'translation':
                correct_answer = translation
                distractor_pool = [trans for key, trans in all_items if trans != correct_answer]

                if len(distractor_pool) >= 2:
                    distractors = random.sample(distractor_pool, 2)
                    options = [correct_answer] + distractors
                    random.shuffle(options)
                    quiz_questions.append({
                        "question": f"'{content}' kelimesinin Türkçe karşılığı nedir?",
                        "options": options,
                        "correct_answer": correct_answer
                    })
                else:

                    error_log.append(
                        f"'{content}' için yeterli çeldirici bulunamadı (en az 2 farklı çeviri daha gerekli).")

        if not quiz_questions and error_log:
            return jsonify({"status": "error",
                            "message": "Sorular üretilirken hatalar oluştu. Detaylar: " + "; ".join(error_log)}), 500

        if not quiz_questions:
            return jsonify({"status": "error",
                            "message": "Seçilen kriterlere uygun soru üretilemedi. Listenizi kontrol edin."}), 500

        return jsonify(quiz_questions)

    except Exception as e:
        print(f"start_quiz içinde kritik hata: {e}")
        return jsonify({"status": "error", "message": "Quiz oluşturulurken beklenmedik bir sunucu hatası oluştu."}), 500


@app.route('/api/translate-text', methods=['POST'])
def translate_text():
    data = request.get_json()
    text_to_translate = data.get('text')

    if not text_to_translate:
        return jsonify({"status": "error", "message": "Çevrilecek metin eksik."}), 400

    try:
        prompt_dosyasi = "prompts/general_system_prompts.json"
        translated_text = list_object_translate(text_to_translate)

        if "Hata:" in translated_text:
            return jsonify({"status": "error", "message": translated_text}), 500

        return jsonify({"status": "success", "translatedText": translated_text})
    except Exception as e:
        print(f"Çeviri sırasında hata: {e}")
        return jsonify({"status": "error", "message": "Çeviri sırasında bir sunucu hatası oluştu."}), 500


@app.route('/api/generate-content', methods=['POST'])
def generate_content():
    data = request.get_json()
    list_name = data.get('listName')
    content_type = data.get('contentType')
    level = data.get('level')

    if not all([list_name, content_type, level]):
        return jsonify(
            {"status": "error", "message": "Eksik parametreler: Liste, içerik tipi veya seviye belirtilmemiş."}), 400

    try:
        file_path = os.path.join(LISTS_DIR, f"{list_name}.json")
        if not os.path.exists(file_path):
            file_path = os.path.join(MAIN_LISTS_DIR, f"{list_name}.json")
            if not os.path.exists(file_path):
                return jsonify({"status": "error", "message": "Liste bulunamadı."}), 404

        with open(file_path, 'r', encoding='utf-8') as f:
            words_data = json.load(f)

        if len(words_data) < 3:
            return jsonify({"status": "error",
                            "message": "Seçtiğiniz listede içerik üretmek için yeterli (en az 3) kelime yok."}), 400

        english_words_for_topic = [key for key in words_data.keys() if is_likely_english(key)]
        if len(english_words_for_topic) < 3:
            return jsonify({"status": "error",
                            "message": "Seçilen listede içerik üretmek için yeterli (en az 3) İngilizce kelime bulunamadı."}), 400

        topic_words = random.sample(english_words_for_topic, 3)
        topic = ", ".join(topic_words)

        prompt_key = ""
        if content_type == 'paragraph':
            prompt_key = "generator_paragraph_prompt"
        elif content_type == 'dialogue':
            prompt_key = "generator_dialogue_prompt"

        if not prompt_key:
            return jsonify({"status": "error", "message": "Geçersiz içerik tipi."}), 400

        # Düzeltilmiş kısım: prompts_data sözlüğü kullanılmalı
        prompt_template = prompts_data.get(prompt_key)
        if not prompt_template:
            return jsonify({"status": "error", "message": f"'{prompt_key}' prompt'u JSON dosyasında bulunamadı."}), 500

        final_prompt = prompt_template.replace("{topic}", topic).replace("{level}", level)

        response = model.generate_content(final_prompt)
        initial_generated_text = response.text

        final_english_text = ensure_english(initial_generated_text)

        return jsonify({"status": "success", "generated_text": final_english_text})

    except Exception as e:
        print(f"İçerik üretilirken hata: {e}")
        return jsonify({"status": "error", "message": f"Sunucuda beklenmedik bir hata oluştu: {e}"}), 500


@app.route('/api/smart-translate', methods=['POST'])
def smart_translate_route():
    data = request.get_json()
    text_to_translate = data.get('text')
    target_level = data.get('level')
    is_academic = data.get('academic', False)

    if not text_to_translate or not target_level:
        return jsonify({"status": "error", "message": "Çevrilecek metin veya seviye eksik."}), 400

    try:
        translated_text = gemini_smart_translate(text_to_translate, target_level, is_academic)

        return jsonify({"status": "success", "translatedText": translated_text})

    except exceptions.ResourceExhausted as e:
        print(f"Gemini Kota Hatası: {e}")
        return jsonify({
            "status": "error",
            "message": "Günlük Gemini API kullanım limitiniz dolmuş. Lütfen daha sonra tekrar deneyin veya API anahtarınızı kontrol edin."
        }), 429

    except Exception as e:
        print(f"Genel Çeviri Hatası: {e}")
        return jsonify({"status": "error", "message": "Çeviri sırasında beklenmedik bir sunucu hatası oluştu."}), 500


if __name__ == "__main__":
    app.run(debug=True)
