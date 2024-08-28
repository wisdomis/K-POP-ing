from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from bs4 import BeautifulSoup
import time
from datetime import datetime, timedelta
import google.generativeai as genai
import sqlite3
import chromedriver_autoinstaller

app = Flask(__name__)
app.secret_key = 'your_secret_key'

# OpenAI API 설정
GOOGLE_API_KEY = 'AIzaSyBlEWYCjt1LSc_r1sykPJS8-7rGrEcyLRc'  # 여기에 새로 발급받은 유효한 API 키를 입력합니다.
genai.configure(api_key=GOOGLE_API_KEY)
generation_config = {
    "temperature": 0.9,
    "top_p": 1,
    "top_k": 1,
    "max_output_tokens": 2048,
}
model = genai.GenerativeModel('gemini-pro', generation_config=generation_config)

# 데이터베이스 초기화
def init_db():
    conn = sqlite3.connect('articles.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS articles (
                id INTEGER PRIMARY KEY,
                stance TEXT,
                paper TEXT,
                title TEXT,
                time TEXT,
                content TEXT,
                link TEXT,
                summary TEXT,
                qa TEXT
                )''')
    conn.commit()
    conn.close()

def save_to_db(data):
    conn = sqlite3.connect('articles.db')
    c = conn.cursor()
    article_ids = []
    for article in data:
        c.execute('''INSERT INTO articles (stance, paper, title, time, content, link, summary, qa) VALUES (?, ?, ?, ?, ?, ?, ?, ?)''', 
        (article['stance'], article['paper'], article['title'], article['time'], article['content'], article['link'], article.get('summary', ''), article.get('qa', '')))
        article_id = c.lastrowid
        article_ids.append(article_id)
    conn.commit()
    conn.close()
    return article_ids

def get_articles_from_db(keyword):
    conn = sqlite3.connect('articles.db')
    c = conn.cursor()
    c.execute('''SELECT * FROM articles WHERE content LIKE ?''', ('%' + keyword + '%',))
    articles = c.fetchall()
    conn.close()
    return articles

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/search', methods=['GET', 'POST'])
def search():
    try:
        print("Search route accessed")  # 디버깅용 출력
        keyword = request.args.get('query') if request.method == 'GET' else request.form['keyword']
        print(f"Keyword: {keyword}")  # 키워드 출력

        if not keyword:
            flash("검색어를 입력해주세요.")
            return redirect(url_for('index'))

        # Chromedriver 자동 설치 및 설정
        chromedriver_autoinstaller.install()
        options = Options()
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        service = Service()

        driver = webdriver.Chrome(service=service, options=options)

        papers = {
            "진보": [("한겨레", "028"), ("경향신문", "032")],
            "중도": [("서울신문", "081"), ("한국일보", "469")],
            "보수": [("조선일보", "023")]
        }

        end_date = datetime.today()
        start_date = end_date - timedelta(days=14)
        all_articles = []

        for single_date in (start_date + timedelta(n) for n in range(14)):
            formatted_date = single_date.strftime("%Y%m%d")
            
            for stance, paper_list in papers.items():
                for paper_name, oid in paper_list:
                    url = f"https://news.naver.com/main/list.naver?mode=LPOD&mid=sec&oid={oid}&listType=title&date={formatted_date}"
                    driver.get(url)
                    
                    soup = BeautifulSoup(driver.page_source, 'html.parser')
                    articles = soup.find_all('a', class_='nclicks(cnt_flashart)')
                    for article in articles:
                        title = article.text.strip()
                        link = article['href']

                        if keyword in title:
                            driver.get(link)
                            time.sleep(1)
                            try:
                                temp_article = driver.find_element(By.CSS_SELECTOR, '#newsct_article').text
                            except:
                                try:
                                    temp_article = driver.find_element(By.CSS_SELECTOR, '._article_content').text
                                except:
                                    continue

                            if temp_article.count(keyword) >= 2:
                                try:
                                    time_e = driver.find_element(By.CSS_SELECTOR, '.media_end_head_info_datestamp_time').text
                                except:
                                    try:
                                        time_e = driver.find_element(By.CSS_SELECTOR, '.NewsEndMain_date__xjtsQ').text
                                    except:
                                        time_e = "시간 정보 없음"

                                all_articles.append({
                                    'stance': stance,
                                    'paper': paper_name,
                                    'title': title,
                                    'time': time_e,
                                    'content': temp_article,
                                    'link': link,
                                    'summary': '',  # 초기값 설정
                                    'qa': ''        # 초기값 설정
                                })

        driver.quit()

        if all_articles:
            for article in all_articles:
                temp_article = article['content']
                prompt = f"다음 기사를 세 줄로 요약해줘:\n{temp_article}"
                response = model.generate_content(prompt)
                article['summary'] = response.text.strip() if response.text else "요약 실패"
            
            save_to_db(all_articles)
        else:
            flash("최근 14일 기준으로 해당 키워드가 포함된 기사가 없습니다.")
            return redirect(url_for('index'))

        return render_template('results.html', keyword=keyword, articles=all_articles)
    except Exception as e:
        print(f"오류 발생: {str(e)}")  # 구체적인 오류 메시지 출력
        flash("서버에 문제가 발생했습니다. 나중에 다시 시도해주세요.")
        return redirect(url_for('index'))

# 회원가입 처리
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        if not username or not password:
            flash('사용자 이름과 비밀번호를 모두 입력해 주세요.')
            return render_template('register.html')

        hashed_password = generate_password_hash(password)

        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        try:
            c.execute('INSERT INTO users (username, password) VALUES (?, ?)', (username, hashed_password))
            conn.commit()
            flash('회원가입이 완료되었습니다.')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('이미 존재하는 사용자입니다.')
        finally:
            conn.close()

    return render_template('register.html')

# 로그인 처리
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute('SELECT password FROM users WHERE username = ?', (username,))
        user = c.fetchone()
        conn.close()

        if user and check_password_hash(user[0], password):
            session['username'] = username
            flash('로그인에 성공했습니다.')
            return redirect(url_for('index'))
        else:
            flash('로그인에 실패했습니다. 다시 시도해주세요.')

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('username', None)
    flash('로그아웃되었습니다.')
    return redirect(url_for('index'))

if __name__ == '__main__':
    init_db()
    app.run(debug=True)
