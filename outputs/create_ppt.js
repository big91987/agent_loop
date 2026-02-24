const pptxgen = require('pptxgenjs');
const path = require('path');

async function createPresentation() {
  const pptx = new pptxgen();
  pptx.layout = 'LAYOUT_16x9';

  // Slide 1: Title Page
  const slide1 = pptx.addSlide();
  
  // Title background
  slide1.addShape(pptx.ShapeType.rect, {
    x: 0, y: 0, w: '100%', h: '100%',
    fill: { color: 'B22234' }
  });
  
  // Title text
  slide1.addText('2024美国大选概览', {
    x: 0.5, y: 1.8, w: '89%', h: 1.2,
    fontSize: 48, bold: true, color: 'FFFFFF', align: 'center'
  });
  
  slide1.addText('U.S. Presidential Election Overview', {
    x: 0.5, y: 3.0, w: '89%', h: 0.7,
    fontSize: 24, color: 'FFFFFF', align: 'center'
  });
  
  // Decorative line
  slide1.addShape(pptx.ShapeType.line, {
    x: 2.6, y: 3.8, w: 3.3, h: 0,
    line: { color: 'FFFFFF', width: 3 }
  });
  
  // Stars decoration
  for (let i = 0; i < 5; i++) {
    slide1.addShape(pptx.ShapeType.star5, {
      x: 2.5 + (i * 1.2), y: 4.1, w: 0.3, h: 0.25,
      fill: { color: '3C3B6E' }
    });
  }
  
  slide1.addText('November 5, 2024', {
    x: 0.5, y: 4.6, w: '89%', h: 0.5,
    fontSize: 18, color: 'FFFFFF', align: 'center'
  });

  // Slide 2: Electoral College & Swing States
  const slide2 = pptx.addSlide();
  
  // Header background
  slide2.addShape(pptx.ShapeType.rect, {
    x: 0, y: 0, w: '100%', h: 0.7,
    fill: { color: 'B22234' }
  });
  
  // Decorative strip
  slide2.addShape(pptx.ShapeType.rect, {
    x: 0, y: 0, w: 0.2, h: 0.7,
    fill: { color: 'FFFFFF' }
  });
  
  slide2.addText('选举制度与关键州', {
    x: 0.5, y: 0.15, w: 8.5, h: 0.4,
    fontSize: 28, bold: true, color: 'FFFFFF'
  });
  
  // Left panel background
  slide2.addShape(pptx.ShapeType.roundRect, {
    x: 0.4, y: 1.0, w: 3.8, h: 3.4,
    fill: { color: 'F0F0F0' },
    shadow: { type: 'outer', blur: 6, offset: 2, angle: 45, opacity: 0.15 }
  });
  
  // Section title 1
  slide2.addShape(pptx.ShapeType.rect, {
    x: 0.6, y: 1.2, w: 3.6, h: 0.02,
    fill: { color: 'B22234' }
  });
  
  slide2.addText('选举人团制度', {
    x: 0.6, y: 1.1, w: 3.6, h: 0.3,
    fontSize: 16, bold: true, color: '3C3B6E'
  });
  
  // Stat box
  slide2.addShape(pptx.ShapeType.roundRect, {
    x: 0.6, y: 1.5, w: 3.6, h: 0.9,
    fill: { color: '3C3B6E' }
  });
  
  slide2.addText('270', {
    x: 0.6, y: 1.55, w: 3.6, h: 0.5,
    fontSize: 32, bold: true, color: 'FFFFFF', align: 'center'
  });
  
  slide2.addText('选举人票获胜门槛', {
    x: 0.6, y: 2.0, w: 3.6, h: 0.25,
    fontSize: 11, color: 'FFFFFF', align: 'center'
  });
  
  // Bullet points 1
  slide2.addText([
    { text: '全美共 538 张选举人票', options: { fontSize: 12, color: '333333', bullet: { type: 'bullet' } } },
    { text: '各州按人口分配选举人票', options: { fontSize: 12, color: '333333', bullet: { type: 'bullet' }, breakLine: true } },
    { text: '除缅因和内布拉斯加外，胜者全得制度', options: { fontSize: 12, color: '333333', bullet: { type: 'bullet' }, breakLine: true } },
    { text: '总统候选人需获270票方可当选', options: { fontSize: 12, color: '333333', bullet: { type: 'bullet' }, breakLine: true } }
  ], {
    x: 0.7, y: 2.6, w: 3.4, h: 1.0
  });
  
  // Section title 2
  slide2.addText('2024年关键日期', {
    x: 0.6, y: 3.0, w: 3.6, h: 0.3,
    fontSize: 16, bold: true, color: '3C3B6E'
  });
  
  slide2.addShape(pptx.ShapeType.rect, {
    x: 0.6, y: 3.28, w: 3.6, h: 0.02,
    fill: { color: 'B22234' }
  });
  
  // Bullet points 2
  slide2.addText([
    { text: '7月 - 民主党全国代表大会', options: { fontSize: 12, color: '333333', bullet: { type: 'bullet' } } },
    { text: '7月 - 共和党全国代表大会', options: { fontSize: 12, color: '333333', bullet: { type: 'bullet' }, breakLine: true } },
    { text: '9月 - 总统辩论', options: { fontSize: 12, color: '333333', bullet: { type: 'bullet' }, breakLine: true } },
    { text: '11月5日 - 投票日', options: { fontSize: 12, color: 'B22234', bold: true, bullet: { type: 'bullet' }, breakLine: true } }
  ], {
    x: 0.7, y: 3.4, w: 3.4, h: 0.9
  });
  
  // Right panel background
  slide2.addShape(pptx.ShapeType.roundRect, {
    x: 4.5, y: 1.0, w: 4.8, h: 3.4,
    fill: { color: 'FFFFFF' },
    shadow: { type: 'outer', blur: 6, offset: 2, angle: 45, opacity: 0.15 }
  });
  
  // Section title 3
  slide2.addShape(pptx.ShapeType.rect, {
    x: 4.7, y: 1.2, w: 4.4, h: 0.02,
    fill: { color: 'B22234' }
  });
  
  slide2.addText('摇摆州地图', {
    x: 4.7, y: 1.1, w: 4.4, h: 0.3,
    fontSize: 16, bold: true, color: '3C3B6E'
  });
  
  // Map placeholder
  slide2.addShape(pptx.ShapeType.roundRect, {
    x: 4.7, y: 1.5, w: 4.4, h: 1.8,
    fill: { color: 'E8E8E8' },
    line: { color: '999999', dashType: 'dash', width: 1.5 }
  });
  
  // Draw simplified swing states visualization
  const swingStates = [
    { name: 'PA', x: 5.8, y: 1.7, votes: 19 },
    { name: 'GA', x: 6.3, y: 2.5, votes: 16 },
    { name: 'MI', x: 5.5, y: 1.9, votes: 15 },
    { name: 'AZ', x: 5.1, y: 2.6, votes: 11 },
    { name: 'WI', x: 5.4, y: 1.6, votes: 10 },
    { name: 'NV', x: 5.0, y: 2.9, votes: 6 },
    { name: 'NC', x: 6.5, y: 2.2, votes: 16 }
  ];
  
  swingStates.forEach(state => {
    slide2.addShape(pptx.ShapeType.roundRect, {
      x: state.x, y: state.y, w: 0.6, h: 0.35,
      fill: { color: '3C3B6E' }
    });
    slide2.addText(state.name, {
      x: state.x, y: state.y + 0.05, w: 0.6, h: 0.25,
      fontSize: 10, bold: true, color: 'FFFFFF', align: 'center'
    });
  });
  
  slide2.addText('7个关键摇摆州', {
    x: 4.7, y: 2.8, w: 4.4, h: 0.4,
    fontSize: 11, color: '666666', align: 'center'
  });
  
  // Section title 4
  slide2.addText('2024摇摆州', {
    x: 4.7, y: 3.0, w: 4.4, h: 0.3,
    fontSize: 16, bold: true, color: '3C3B6E'
  });
  
  // Bullet points 3
  slide2.addText([
    { text: '宾夕法尼亚 - 19票', options: { fontSize: 11, color: 'B22234', bold: true, bullet: { type: 'bullet' } } },
    { text: '乔治亚 - 16票', options: { fontSize: 11, color: '333333', bullet: { type: 'bullet' }, breakLine: true } },
    { text: '密歇根 - 15票', options: { fontSize: 11, color: '333333', bullet: { type: 'bullet' }, breakLine: true } },
    { text: '亚利桑那 - 11票', options: { fontSize: 11, color: '333333', bullet: { type: 'bullet' }, breakLine: true } },
    { text: '威斯康星 - 10票', options: { fontSize: 11, color: '333333', bullet: { type: 'bullet' }, breakLine: true } },
    { text: '内华达 - 6票', options: { fontSize: 11, color: '333333', bullet: { type: 'bullet' }, breakLine: true } },
    { text: '北卡罗来纳 - 16票', options: { fontSize: 11, color: '333333', bullet: { type: 'bullet' }, breakLine: true } }
  ], {
    x: 4.8, y: 3.4, w: 4.2, h: 0.9
  });
  
  slide2.addText('* 摇摆州投票结果往往决定最终选举走向', {
    x: 4.7, y: 4.25, w: 4.4, h: 0.2,
    fontSize: 9, italic: true, color: '666666', align: 'center'
  });

  // Save presentation
  const outputPath = path.resolve(__dirname, 'deepagents_us_election_20260214_155422.pptx');
  await pptx.writeFile(outputPath);
  console.log('Presentation created:', outputPath);
}

createPresentation().catch(console.error);
