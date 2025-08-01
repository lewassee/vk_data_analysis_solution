#!/usr/bin/env python3
"""
VK Data Analysis Web Interface - Веб-интерфейс для демонстрации анализа данных VK
Предоставляет удобный интерфейс для просмотра результатов анализа и управления парсингом
"""

from flask import Flask, render_template, jsonify, request, send_file, redirect, url_for
from flask_cors import CORS
import json
import os
from datetime import datetime
import pandas as pd
from vk_parser import VKGroupParser
from data_analyzer import VKDataAnalyzer
import threading
import time

app = Flask(__name__)
CORS(app)

# Глобальные переменные для отслеживания состояния
parsing_status = {
    'is_running': False,
    'progress': 0,
    'message': '',
    'last_update': None
}

@app.route('/')
def index():
    """Главная страница"""
    return render_template('index.html')

@app.route('/api/status')
def get_status():
    """Получение статуса парсинга"""
    return jsonify(parsing_status)

@app.route('/api/start_parsing', methods=['POST'])
def start_parsing():
    """Запуск парсинга данных"""
    global parsing_status
    
    if parsing_status['is_running']:
        return jsonify({'error': 'Парсинг уже выполняется'}), 400
    
    data = request.get_json()
    access_token = data.get('access_token')
    group_id = data.get('group_id', 'big_asu')
    max_posts = int(data.get('max_posts', 100))
    start_date = data.get('start_date')  # Формат: YYYY-MM-DD
    end_date = data.get('end_date')      # Формат: YYYY-MM-DD
    
    if not access_token:
        return jsonify({'error': 'Требуется токен доступа'}), 400
    
    # Запускаем парсинг в отдельном потоке
    thread = threading.Thread(target=run_parsing, args=(access_token, group_id, max_posts, start_date, end_date))
    thread.daemon = True
    thread.start()
    
    return jsonify({'message': 'Парсинг запущен'})

def run_parsing(access_token, group_id, max_posts, start_date=None, end_date=None):
    """Функция для выполнения парсинга в отдельном потоке"""
    global parsing_status
    
    try:
        parsing_status.update({
            'is_running': True,
            'progress': 0,
            'message': 'Инициализация парсера...',
            'last_update': datetime.now().isoformat()
        })
        
        parser = VKGroupParser(access_token)
        
        parsing_status.update({
            'progress': 10,
            'message': 'Получение информации о группе...'
        })
        
        # Преобразуем строки дат в объекты datetime если они переданы
        start_datetime = None
        end_datetime = None
        
        if start_date:
            try:
                start_datetime = datetime.strptime(start_date, '%Y-%m-%d')
                parsing_status.update({
                    'message': f'Фильтрация с {start_date}...'
                })
            except ValueError:
                pass
        
        if end_date:
            try:
                end_datetime = datetime.strptime(end_date, '%Y-%m-%d')
                if start_datetime:
                    parsing_status.update({
                        'message': f'Фильтрация периода {start_date} - {end_date}...'
                    })
                else:
                    parsing_status.update({
                        'message': f'Фильтрация до {end_date}...'
                    })
            except ValueError:
                pass
        
        # Получаем данные
        data = parser.parse_group_data(
            group_id=group_id,
            max_posts=max_posts,
            include_comments=True,
            start_date=start_datetime,
            end_date=end_datetime
        )
        
        parsing_status.update({
            'progress': 80,
            'message': 'Сохранение данных...'
        })
        
        # Сохраняем данные
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        os.makedirs('vk_data', exist_ok=True)
        
        data_file = f'vk_data/{group_id}_data_{timestamp}.json'
        parser.save_to_json(data, data_file)
        parser.save_to_csv(
            data,
            f'vk_data/{group_id}_posts_{timestamp}.csv',
            f'vk_data/{group_id}_comments_{timestamp}.csv'
        )
        
        parsing_status.update({
            'progress': 90,
            'message': 'Анализ данных...'
        })
        
        # Запускаем анализ
        analyzer = VKDataAnalyzer(data_file)
        os.makedirs('analysis_results', exist_ok=True)
        analyzer.generate_report('analysis_results/latest_analysis.json')
        analyzer.create_visualizations('analysis_results')
        
        # Формируем сообщение о результатах
        result_message = f'Парсинг завершен! Собрано {data["total_posts"]} постов и {data["total_comments"]} комментариев'
        
        if data.get('filter_period', {}).get('start_date'):
            period_info = data['filter_period']
            result_message += f' за период {period_info["start_date"][:10]} - {period_info["end_date"][:10]}'
            result_message += f' (постов в периоде: {period_info["posts_in_period"]})'
        
        parsing_status.update({
            'is_running': False,
            'progress': 100,
            'message': result_message,
            'last_update': datetime.now().isoformat()
        })
        
    except Exception as e:
        parsing_status.update({
            'is_running': False,
            'progress': 0,
            'message': f'Ошибка: {str(e)}',
            'last_update': datetime.now().isoformat()
        })

@app.route('/api/analysis_report')
def get_analysis_report():
    """Получение отчета анализа"""
    try:
        with open('analysis_results/latest_analysis.json', 'r', encoding='utf-8') as f:
            report = json.load(f)
        return jsonify(report)
    except FileNotFoundError:
        return jsonify({'error': 'Отчет не найден. Запустите анализ данных.'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/visualizations')
def get_visualizations():
    """Получение списка доступных визуализаций"""
    viz_dir = 'analysis_results'
    visualizations = []
    
    if os.path.exists(viz_dir):
        for file in os.listdir(viz_dir):
            if file.endswith('.png'):
                visualizations.append({
                    'name': file,
                    'title': file.replace('_', ' ').replace('.png', '').title(),
                    'url': f'/api/image/{file}'
                })
    
    return jsonify(visualizations)

@app.route('/api/image/<filename>')
def get_image(filename):
    """Получение изображения визуализации"""
    try:
        return send_file(f'analysis_results/{filename}', mimetype='image/png')
    except FileNotFoundError:
        return jsonify({'error': 'Изображение не найдено'}), 404

@app.route('/api/data_files')
def get_data_files():
    """Получение списка файлов с данными"""
    data_dir = 'vk_data'
    files = []
    
    if os.path.exists(data_dir):
        for file in os.listdir(data_dir):
            if file.endswith('.json'):
                file_path = os.path.join(data_dir, file)
                stat = os.stat(file_path)
                files.append({
                    'name': file,
                    'size': stat.st_size,
                    'modified': datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    'download_url': f'/api/download/{file}'
                })
    
    files.sort(key=lambda x: x['modified'], reverse=True)
    return jsonify(files)

@app.route('/api/download/<filename>')
def download_file(filename):
    """Скачивание файла с данными"""
    try:
        return send_file(f'vk_data/{filename}', as_attachment=True)
    except FileNotFoundError:
        return jsonify({'error': 'Файл не найден'}), 404

# HTML шаблон для веб-интерфейса
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>VK Data Analysis - Анализ данных ВКонтакте</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            color: #333;
        }
        
        .container {
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
        }
        
        .header {
            text-align: center;
            color: white;
            margin-bottom: 30px;
        }
        
        .header h1 {
            font-size: 2.5em;
            margin-bottom: 10px;
        }
        
        .header p {
            font-size: 1.2em;
            opacity: 0.9;
        }
        
        .card {
            background: white;
            border-radius: 15px;
            padding: 25px;
            margin-bottom: 20px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.1);
        }
        
        .card h2 {
            color: #4a5568;
            margin-bottom: 20px;
            font-size: 1.5em;
        }
        
        .form-group {
            margin-bottom: 15px;
        }
        
        .form-group label {
            display: block;
            margin-bottom: 5px;
            font-weight: 600;
            color: #4a5568;
        }
        
        .form-group input, .form-group select {
            width: 100%;
            padding: 12px;
            border: 2px solid #e2e8f0;
            border-radius: 8px;
            font-size: 16px;
            transition: border-color 0.3s;
        }
        
        .form-group input:focus, .form-group select:focus {
            outline: none;
            border-color: #667eea;
        }
        
        .btn {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            padding: 12px 24px;
            border-radius: 8px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: transform 0.2s;
        }
        
        .btn:hover {
            transform: translateY(-2px);
        }
        
        .btn:disabled {
            opacity: 0.6;
            cursor: not-allowed;
            transform: none;
        }
        
        .progress-bar {
            width: 100%;
            height: 20px;
            background: #e2e8f0;
            border-radius: 10px;
            overflow: hidden;
            margin: 15px 0;
        }
        
        .progress-fill {
            height: 100%;
            background: linear-gradient(90deg, #667eea, #764ba2);
            transition: width 0.3s ease;
        }
        
        .status {
            padding: 15px;
            border-radius: 8px;
            margin: 15px 0;
        }
        
        .status.success {
            background: #f0fff4;
            border: 1px solid #9ae6b4;
            color: #22543d;
        }
        
        .status.error {
            background: #fed7d7;
            border: 1px solid #feb2b2;
            color: #742a2a;
        }
        
        .status.info {
            background: #ebf8ff;
            border: 1px solid #90cdf4;
            color: #2a4365;
        }
        
        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
        }
        
        .stat-card {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            border-radius: 12px;
            text-align: center;
        }
        
        .stat-number {
            font-size: 2.5em;
            font-weight: bold;
            margin-bottom: 5px;
        }
        
        .stat-label {
            opacity: 0.9;
            font-size: 1.1em;
        }
        
        .visualization {
            text-align: center;
            margin: 20px 0;
        }
        
        .visualization img {
            max-width: 100%;
            height: auto;
            border-radius: 8px;
            box-shadow: 0 5px 15px rgba(0,0,0,0.1);
        }
        
        .hidden {
            display: none;
        }
        
        .loading {
            text-align: center;
            padding: 40px;
        }
        
        .spinner {
            border: 4px solid #f3f3f3;
            border-top: 4px solid #667eea;
            border-radius: 50%;
            width: 40px;
            height: 40px;
            animation: spin 1s linear infinite;
            margin: 0 auto 20px;
        }
        
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🔍 VK Data Analysis</h1>
            <p>Система анализа данных из групп ВКонтакте по АСУ ТП</p>
        </div>
        
        <div class="card">
            <h2>📊 Парсинг данных</h2>
            <form id="parsingForm">
                <div class="form-group">
                    <label for="accessToken">Токен доступа VK API:</label>
                    <input type="text" id="accessToken" placeholder="Введите ваш токен доступа" required>
                </div>
                
                <div class="form-group">
                    <label for="groupId">ID группы:</label>
                    <input type="text" id="groupId" value="big_asu" placeholder="Например: big_asu">
                </div>
                
                <div class="form-group">
                    <label for="maxPosts">Максимальное количество постов:</label>
                    <select id="maxPosts">
                        <option value="50">50 постов</option>
                        <option value="100" selected>100 постов</option>
                        <option value="200">200 постов</option>
                        <option value="500">500 постов</option>
                    </select>
                </div>
                
                <div class="form-group">
                    <label for="dateFilter">Фильтр по дате:</label>
                    <select id="dateFilter" onchange="toggleDateInputs()">
                        <option value="all">Все посты</option>
                        <option value="last_week">Последняя неделя</option>
                        <option value="last_month">Последний месяц</option>
                        <option value="last_3_months">Последние 3 месяца</option>
                        <option value="custom">Выбрать период</option>
                    </select>
                </div>
                
                <div id="customDateRange" class="hidden">
                    <div class="form-group">
                        <label for="startDate">Начальная дата:</label>
                        <input type="date" id="startDate">
                    </div>
                    
                    <div class="form-group">
                        <label for="endDate">Конечная дата:</label>
                        <input type="date" id="endDate">
                    </div>
                </div>
                
                <button type="submit" class="btn" id="startBtn">🚀 Запустить парсинг</button>
            </form>
            
            <div id="progressSection" class="hidden">
                <div class="progress-bar">
                    <div class="progress-fill" id="progressFill" style="width: 0%"></div>
                </div>
                <div id="statusMessage" class="status info">Инициализация...</div>
            </div>
        </div>
        
        <div id="resultsSection" class="hidden">
            <div class="card">
                <h2>📈 Результаты анализа</h2>
                <div id="statsGrid" class="grid"></div>
            </div>
            
            <div class="card">
                <h2>📊 Визуализации</h2>
                <div id="visualizations"></div>
            </div>
            
            <div class="card">
                <h2>💾 Файлы данных</h2>
                <div id="dataFiles"></div>
            </div>
        </div>
    </div>
    
    <script>
        let statusCheckInterval;
        
        document.getElementById('parsingForm').addEventListener('submit', function(e) {
            e.preventDefault();
            startParsing();
        });
        
        function toggleDateInputs() {
            const dateFilter = document.getElementById('dateFilter').value;
            const customDateRange = document.getElementById('customDateRange');
            
            if (dateFilter === 'custom') {
                customDateRange.classList.remove('hidden');
            } else {
                customDateRange.classList.add('hidden');
            }
        }
        
        function calculateDateRange(filterType) {
            const now = new Date();
            let startDate = null;
            let endDate = now.toISOString().split('T')[0]; // Сегодня
            
            switch (filterType) {
                case 'last_week':
                    startDate = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
                    break;
                case 'last_month':
                    startDate = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
                    break;
                case 'last_3_months':
                    startDate = new Date(now.getTime() - 90 * 24 * 60 * 60 * 1000);
                    break;
                default:
                    return { start_date: null, end_date: null };
            }
            
            return {
                start_date: startDate.toISOString().split('T')[0],
                end_date: endDate
            };
        }
        
        function startParsing() {
            const accessToken = document.getElementById('accessToken').value;
            const groupId = document.getElementById('groupId').value;
            const maxPosts = document.getElementById('maxPosts').value;
            const dateFilter = document.getElementById('dateFilter').value;
            
            if (!accessToken) {
                alert('Пожалуйста, введите токен доступа');
                return;
            }
            
            let startDate = null;
            let endDate = null;
            
            if (dateFilter === 'custom') {
                startDate = document.getElementById('startDate').value;
                endDate = document.getElementById('endDate').value;
                
                if (startDate && endDate && startDate > endDate) {
                    alert('Начальная дата не может быть позже конечной даты');
                    return;
                }
            } else if (dateFilter !== 'all') {
                const dateRange = calculateDateRange(dateFilter);
                startDate = dateRange.start_date;
                endDate = dateRange.end_date;
            }
            
            const startBtn = document.getElementById('startBtn');
            startBtn.disabled = true;
            startBtn.textContent = '⏳ Запуск...';
            
            document.getElementById('progressSection').classList.remove('hidden');
            document.getElementById('resultsSection').classList.add('hidden');
            
            const requestData = {
                access_token: accessToken,
                group_id: groupId,
                max_posts: maxPosts
            };
            
            if (startDate) requestData.start_date = startDate;
            if (endDate) requestData.end_date = endDate;
            
            fetch('/api/start_parsing', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(requestData)
            })
            .then(response => response.json())
            .then(data => {
                if (data.error) {
                    showError(data.error);
                    resetForm();
                } else {
                    startStatusCheck();
                }
            })
            .catch(error => {
                showError('Ошибка запуска парсинга: ' + error.message);
                resetForm();
            });
        }
        
        function startStatusCheck() {
            statusCheckInterval = setInterval(checkStatus, 1000);
        }
        
        function checkStatus() {
            fetch('/api/status')
                .then(response => response.json())
                .then(status => {
                    updateProgress(status.progress);
                    updateStatusMessage(status.message, status.is_running ? 'info' : 'success');
                    
                    if (!status.is_running && status.progress === 100) {
                        clearInterval(statusCheckInterval);
                        resetForm();
                        loadResults();
                    } else if (!status.is_running && status.progress === 0) {
                        clearInterval(statusCheckInterval);
                        resetForm();
                    }
                })
                .catch(error => {
                    console.error('Ошибка проверки статуса:', error);
                });
        }
        
        function updateProgress(progress) {
            document.getElementById('progressFill').style.width = progress + '%';
        }
        
        function updateStatusMessage(message, type = 'info') {
            const statusEl = document.getElementById('statusMessage');
            statusEl.textContent = message;
            statusEl.className = 'status ' + type;
        }
        
        function resetForm() {
            const startBtn = document.getElementById('startBtn');
            startBtn.disabled = false;
            startBtn.textContent = '🚀 Запустить парсинг';
        }
        
        function showError(message) {
            updateStatusMessage('Ошибка: ' + message, 'error');
        }
        
        function loadResults() {
            document.getElementById('resultsSection').classList.remove('hidden');
            
            // Загружаем статистику
            fetch('/api/analysis_report')
                .then(response => response.json())
                .then(report => {
                    displayStats(report.basic_statistics);
                })
                .catch(error => {
                    console.error('Ошибка загрузки отчета:', error);
                });
            
            // Загружаем визуализации
            fetch('/api/visualizations')
                .then(response => response.json())
                .then(visualizations => {
                    displayVisualizations(visualizations);
                })
                .catch(error => {
                    console.error('Ошибка загрузки визуализаций:', error);
                });
            
            // Загружаем список файлов
            fetch('/api/data_files')
                .then(response => response.json())
                .then(files => {
                    displayDataFiles(files);
                })
                .catch(error => {
                    console.error('Ошибка загрузки файлов:', error);
                });
        }
        
        function displayStats(stats) {
            const statsGrid = document.getElementById('statsGrid');
            statsGrid.innerHTML = `
                <div class="stat-card">
                    <div class="stat-number">${stats.total_posts}</div>
                    <div class="stat-label">Постов собрано</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number">${stats.total_comments}</div>
                    <div class="stat-label">Комментариев собрано</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number">${Math.round(stats.engagement_stats.avg_likes_per_post)}</div>
                    <div class="stat-label">Среднее лайков на пост</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number">${Math.round(stats.engagement_stats.avg_comments_per_post)}</div>
                    <div class="stat-label">Среднее комментариев на пост</div>
                </div>
            `;
        }
        
        function displayVisualizations(visualizations) {
            const vizContainer = document.getElementById('visualizations');
            vizContainer.innerHTML = '';
            
            visualizations.forEach(viz => {
                const vizDiv = document.createElement('div');
                vizDiv.className = 'visualization';
                vizDiv.innerHTML = `
                    <h3>${viz.title}</h3>
                    <img src="${viz.url}" alt="${viz.title}" loading="lazy">
                `;
                vizContainer.appendChild(vizDiv);
            });
        }
        
        function displayDataFiles(files) {
            const filesContainer = document.getElementById('dataFiles');
            filesContainer.innerHTML = '';
            
            if (files.length === 0) {
                filesContainer.innerHTML = '<p>Файлы данных не найдены</p>';
                return;
            }
            
            const filesList = document.createElement('ul');
            filesList.style.listStyle = 'none';
            filesList.style.padding = '0';
            
            files.forEach(file => {
                const fileItem = document.createElement('li');
                fileItem.style.padding = '10px';
                fileItem.style.borderBottom = '1px solid #e2e8f0';
                fileItem.innerHTML = `
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <div>
                            <strong>${file.name}</strong><br>
                            <small>Размер: ${(file.size / 1024 / 1024).toFixed(2)} MB | 
                            Изменен: ${new Date(file.modified).toLocaleString()}</small>
                        </div>
                        <a href="${file.download_url}" class="btn" style="text-decoration: none;">📥 Скачать</a>
                    </div>
                `;
                filesList.appendChild(fileItem);
            });
            
            filesContainer.appendChild(filesList);
        }
        
        // Проверяем наличие результатов при загрузке страницы
        window.addEventListener('load', function() {
            fetch('/api/analysis_report')
                .then(response => {
                    if (response.ok) {
                        loadResults();
                    }
                })
                .catch(error => {
                    // Результатов пока нет, это нормально
                });
        });
    </script>
</body>
</html>
'''

# Создаем директорию для шаблонов
os.makedirs('templates', exist_ok=True)
with open('templates/index.html', 'w', encoding='utf-8') as f:
    f.write(HTML_TEMPLATE)

if __name__ == '__main__':
    print("🚀 Запуск веб-интерфейса VK Data Analysis...")
    print("📊 Откройте браузер и перейдите по адресу: http://localhost:5000")
    print("🔍 Для остановки нажмите Ctrl+C")
    
    app.run(host='0.0.0.0', port=5000, debug=False)

