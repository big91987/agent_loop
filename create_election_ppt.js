const pptxgen = require('pptxgenjs');

async function createPresentation() {
    const pptx = new pptxgen();
    pptx.layout = 'LAYOUT_16x9';
    pptx.author = 'pi-mono';
    pptx.title = '美国大选概览';

    // Slide 1: 封面 - 美国大选概览
    const slide1 = pptx.addSlide();
    
    // 背景
    slide1.addShape(pptx.shapes.RECTANGLE, {
        x: 0, y: 0, w: '100%', h: '100%',
        fill: { color: '1C2833' }
    });
    
    // 标题
    slide1.addText('美国大选概览', {
        x: 0.5, y: 1.5, w: 9, h: 1.5,
        fontSize: 44, color: 'FFFFFF', bold: true, align: 'center'
    });
    
    // 副标题
    slide1.addText('2024年总统选举与政治格局', {
        x: 0.5, y: 3, w: 9, h: 0.8,
        fontSize: 24, color: 'AAB7B8', align: 'center'
    });
    
    // 装饰线
    slide1.addShape(pptx.shapes.RECTANGLE, {
        x: 2, y: 4, w: 6, h: 0.05,
        fill: { color: '4472C4' }
    });
    
    // 关键日期
    slide1.addText([
        { text: '初选阶段: 2024年1月-6月', options: { fontSize: 16, color: 'F4F6F6' } },
        { text: '全国代表大会: 2024年7月-8月', options: { fontSize: 16, color: 'F4F6F6' } },
        { text: '竞选活动: 2024年9月-11月', options: { fontSize: 16, color: 'F4F6F6' } },
        { text: '选举日: 2024年11月5日', options: { fontSize: 16, color: 'F39C12', bold: true } }
    ], {
        x: 2, y: 4.5, w: 6, h: 2.5, align: 'center'
    });

    // Slide 2: 选举制度与两党概况
    const slide2 = pptx.addSlide();
    
    // 背景
    slide2.addShape(pptx.shapes.RECTANGLE, {
        x: 0, y: 0, w: '100%', h: '100%',
        fill: { color: 'F4F6F6' }
    });
    
    // 标题
    slide2.addText('选举制度与主要政党', {
        x: 0.5, y: 0.4, w: 9, h: 0.8,
        fontSize: 32, color: '1C2833', bold: true
    });
    
    // 左侧 - 选举人团制度
    slide2.addShape(pptx.shapes.ROUNDED_RECTANGLE, {
        x: 0.5, y: 1.5, w: 4.2, h: 3,
        fill: { color: 'FFFFFF' },
        line: { color: '4472C4', width: 2 },
        rectRadius: 0.2
    });
    
    slide2.addText('选举人团制度', {
        x: 0.8, y: 1.7, w: 3.9, h: 0.6,
        fontSize: 20, color: '4472C4', bold: true
    });
    
    slide2.addText([
        { text: '• 538张选举人票', options: { fontSize: 14, color: '2E4053' } },
        { text: '• 获得270票即可获胜', options: { fontSize: 14, color: '2E4053' } },
        { text: '• 50州+华盛顿特区', options: { fontSize: 14, color: '2E4053' } },
        { text: '• 赢者通吃规则(多数州)', options: { fontSize: 14, color: '2E4053' } },
        { text: '• 关键摇摆州决定结果', options: { fontSize: 14, color: '2E4053', bold: true } }
    ], {
        x: 0.8, y: 2.4, w: 3.9, h: 2
    });
    
    // 右侧 - 两党对比
    slide2.addShape(pptx.shapes.ROUNDED_RECTANGLE, {
        x: 5.3, y: 1.5, w: 4.2, h: 3,
        fill: { color: 'FFFFFF' },
        line: { color: 'ED7D31', width: 2 },
        rectRadius: 0.2
    });
    
    slide2.addText('民主党 & 共和党', {
        x: 5.6, y: 1.7, w: 3.6, h: 0.6,
        fontSize: 20, color: 'ED7D31', bold: true
    });
    
    slide2.addText([
        { text: '民主党 (蓝)', options: { fontSize: 14, color: '3498DB', bold: true } },
        { text: '• 进步派政策立场', options: { fontSize: 13, color: '2E4053' } },
        { text: '• 强调社会福利与环境', options: { fontSize: 13, color: '2E4053' } },
        { text: '', options: { fontSize: 8 } },
        { text: '共和党 (红)', options: { fontSize: 14, color: 'E74C3C', bold: true } },
        { text: '• 保守派政策立场', options: { fontSize: 13, color: '2E4053' } },
        { text: '• 强调经济增长与安全', options: { fontSize: 13, color: '2E4053' } }
    ], {
        x: 5.6, y: 2.4, w: 3.6, h: 2
    });
    
    // 底部 - 摇摆州提示
    slide2.addShape(pptx.shapes.RECTANGLE, {
        x: 0.5, y: 4.8, w: 9, h: 0.5,
        fill: { color: 'FFE1C7' },
        line: { color: 'E3B448', width: 1 }
    });
    
    slide2.addText('关键摇摆州: 宾夕法尼亚、威斯康星、密歇根、亚利桑那、乔治亚、内华达', {
        x: 0.5, y: 4.9, w: 9, h: 0.4,
        fontSize: 14, color: '5D1D2E', bold: true, align: 'center'
    });

    // 保存文件
    const outputPath = '/Users/admin/work/agent_loop/outputs/pi_mono_us_election_20260214_172522.pptx';
    await pptx.writeFile({ fileName: outputPath });
    console.log(`PPT已生成: ${outputPath}`);
}

createPresentation().catch(console.error);
