import ollama
import os
import streamlit as st
import xml.etree.ElementTree as ET
from datetime import datetime
import re
from streamlit_extras.app_logo import add_logo
import shutil
import altair as alt
import pandas as pd

# 设置页面配置
st.set_page_config(page_title="图片美学评分工具", layout="wide")

# 自定义CSS
st.markdown("""
<style>
    .stButton > button {
        width: 100%;
    }
    .css-1v0mbdj.etr89bj1 {
        display: flex;
        justify-content: center;
        align-items: center;
    }
    .css-1v0mbdj.etr89bj1 img {
        max-width: 200px;
    }
    .card {
        box-shadow: 0 4px 8px 0 rgba(0,0,0,0.2);
        transition: 0.3s;
        border-radius: 5px;
        padding: 20px;
        margin: 10px 0;
    }
    .card:hover {
        box-shadow: 0 8px 16px 0 rgba(0,0,0,0.2);
    }
</style>
""", unsafe_allow_html=True)

# 初始化 session_state
if 'results' not in st.session_state:
    st.session_state.results = []
if 'processed_images' not in st.session_state:
    st.session_state.processed_images = set()

def rate_image_aesthetics(image_path, model_id):
    prompt = """
    请分析这张图片的美学质量,并给出1-10分的评分。
    请使用以下XML格式输出你的分析:
    <aesthetic_rating>
        <score>你的评分(1-10之间的数字)</score>
        <description>对图片内容的简要描述</description>
        <analysis>
            评分理由,包括构图、色彩、主题等方面的分析。
        </analysis>
    </aesthetic_rating>
    请确保你的回答严格遵循这个XML格式,并将总字数控制在300字以内。
    """
    
    try:
        res = ollama.chat(
            model=model_id,
            messages=[
                {
                    'role': 'user',
                    'content': prompt,
                    'images': [image_path]
                }
            ]
        )
        return res['message']['content']
    except Exception as e:
        st.error(f"处理图片时出错: {str(e)}")
        return f"<aesthetic_rating><score>0</score><description>处理出错</description><analysis>错误: {str(e)}</analysis></aesthetic_rating>"

def extract_score_from_text(text):
    match = re.search(r'<score>([\d.]+)</score>', text)
    if match:
        return float(match.group(1))
    else:
        return 0

def process_image(image_path, model_id):
    if image_path in st.session_state.processed_images:
        return next((r for r in st.session_state.results if r['filename'] == os.path.basename(image_path)), None)

    result = rate_image_aesthetics(image_path, model_id)
    
    output_path = os.path.splitext(image_path)[0] + '.txt'
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(result)
    
    try:
        root = ET.fromstring(result)
        score_element = root.find('score')
        if score_element is not None:
            score = float(score_element.text)
        else:
            score = 0
    except ET.ParseError:
        score = extract_score_from_text(result)
    
    processed_result = {
        'filename': os.path.basename(image_path),
        'score': score,
        'result': f"Processed: {image_path}\nResult saved to {output_path}\n"
    }
    
    st.session_state.results.append(processed_result)
    st.session_state.processed_images.add(image_path)
    
    return processed_result

def process_folder(folder_path, model_id):
    for filename in os.listdir(folder_path):
        if filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp')):
            image_path = os.path.join(folder_path, filename)
            process_image(image_path, model_id)

def save_analysis_results(folder_path, results, score_threshold):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_filename = f"analysis_results_{timestamp}.txt"
    output_path = os.path.join(folder_path, output_filename)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(f"分析结果 - 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write(f"总共处理的图片数量: {len(results)}\n")
        
        zero_score_images = [result for result in results if result['score'] == 0]
        low_score_images = [result for result in results if 0 < result['score'] < score_threshold]
        
        f.write(f"评分为0分的图片数量: {len(zero_score_images)}\n")
        f.write(f"评分在0到{score_threshold}分之间的图片数量: {len(low_score_images)}\n\n")
        
        if zero_score_images:
            f.write("评分为0分的图片:\n")
            for img in zero_score_images:
                f.write(f"{img['filename']} - 评分: 0\n")
            f.write("\n")
        
        if low_score_images:
            f.write(f"评分在0到{score_threshold}分之间的图片:\n")
            for img in low_score_images:
                f.write(f"{img['filename']} - 评分: {img['score']}\n")
        else:
            f.write(f"没有评分在0到{score_threshold}分之间的图片。\n")
    
    return output_path

def delete_low_score_images(folder_path, results, score_threshold):
    low_score_images = [result for result in results if result['score'] < score_threshold]
    deleted_count = 0
    for img in low_score_images:
        file_path = os.path.join(folder_path, img['filename'])
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                deleted_count += 1
            except Exception as e:
                st.error(f"删除文件 {img['filename']} 时出错: {str(e)}")
    
    # 更新结果列表，移除已删除的图片
    updated_results = [result for result in results if result['score'] >= score_threshold]
    return deleted_count, updated_results

# Streamlit 界面
st.title('📸 图片美学评分工具')

col1, col2 = st.columns(2)

with col1:
    model_id = st.text_input('🤖 模型名称', value='llava-llama3:8b-v1.1-fp16')
    folder_path = st.text_input('📁 图片文件夹路径', value=r'C:\Users\yl\Downloads\test')

with col2:
    score_threshold = st.slider('📊 评分阈值', min_value=1.0, max_value=10.0, value=6.0, step=0.1)

col1, col2, col3 = st.columns([4, 1, 1])

with col1:
    if st.button('🚀 开始处理', type="primary"):
        if os.path.isdir(folder_path):
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            image_files = [f for f in os.listdir(folder_path) if f.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp'))]
            total_files = len(image_files)
            for i, filename in enumerate(image_files):
                image_path = os.path.join(folder_path, filename)
                process_image(image_path, model_id)
                progress = (i + 1) / total_files
                progress_bar.progress(progress)
                status_text.text(f'处理进度: {int(progress * 100)}%')
            
            progress_bar.empty()
            status_text.success('处理完成!')
            
            zero_score_images = [result for result in st.session_state.results if result['score'] == 0]
            low_score_images = [result for result in st.session_state.results if 0 < result['score'] < score_threshold]
            
            st.subheader('评分分析')
            st.write(f'总共处理的图片数量: {len(st.session_state.results)}')
            st.write(f'评分为0分的图片数量: {len(zero_score_images)}')
            st.write(f'评分在0到{score_threshold}分之间的图片数量: {len(low_score_images)}')
            
            output_path = save_analysis_results(folder_path, st.session_state.results, score_threshold)
            st.success(f'分析结果已保存到: {output_path}')
            
        else:
            st.error('无效的文件夹路径，请检查输入。')

with col2:
    if st.button('🧹 清除结果'):
        st.session_state.results = []
        st.session_state.processed_images = set()
        st.success('所有结果已清除')

with col3:
    if st.button('🗑 删除低分图片'):
        if st.session_state.results:
            deleted_count, updated_results = delete_low_score_images(folder_path, st.session_state.results, score_threshold)
            st.session_state.results = updated_results
            st.success(f'成功删除了 {deleted_count} 张低分图片')
            st.toast('结果列表已更新，请重新查看结果')
        else:
            st.toast('没有可删除的图片，请先处理图片')

# 显示结果
if st.session_state.results:
    st.subheader('📊 处理结果')
    
    zero_score_images = [result for result in st.session_state.results if result['score'] == 0]
    low_score_images = [result for result in st.session_state.results if 0 < result['score'] < score_threshold]
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("总处理图片数量", len(st.session_state.results))
    with col2:
        st.metric("评分为0分的图片数量", len(zero_score_images))
    with col3:
        st.metric(f"评分 < {score_threshold} 的图片数量", len(low_score_images))
    
    # 使用Altair创建评分分布图表
    df = pd.DataFrame([{'filename': r['filename'], 'score': r['score']} for r in st.session_state.results])
    chart = alt.Chart(df).mark_bar().encode(
        x=alt.X('score:Q', bin=True),
        y='count()',
    ).properties(
        title='评分分布'
    )
    st.altair_chart(chart, use_container_width=True)
    
    if zero_score_images:
        st.subheader('评分为0分的图片:')
        for img in zero_score_images:
            with st.expander(f"{img['filename']} - 评分: 0"):
                st.image(os.path.join(folder_path, img['filename']), use_column_width=True)
    
    if low_score_images:
        st.subheader(f'评分在0到{score_threshold}分之间的图片:')
        for img in low_score_images:
            with st.expander(f"{img['filename']} - 评分: {img['score']}"):
                st.image(os.path.join(folder_path, img['filename']), use_column_width=True)
    else:
        st.info(f'没有评分在0到{score_threshold}分之间的图片。')