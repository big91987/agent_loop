const pptxgen = require("pptxgenjs");
const fs = require("fs");
const path = require("path");

// 确保输出目录存在
const outputDir = "/Users/admin/work/agent_loop/outputs";
if (!fs.existsSync(outputDir)) {
  fs.mkdirSync(outputDir, { recursive: true });
}

// 创建 PPT
let pres = new pptxgen();

// 第1页: 美国大选概述
let slide1 = pres.addSlide();
slide1.addText("2024年美国大选概述", { 
  x: 0.5, y: 0.5, w: 8.5, h: 1, 
  fontSize: 32, bold: true, color: "1E3A5F",
  align: "center" 
});
slide1.addText("选举日期: 2024年11月5日", { 
  x: 1, y: 1.8, w: 7.5, h: 0.6, 
  fontSize: 18, color: "333333" 
});
slide1.addText("主要候选人: 卡玛拉·哈里斯 (民主党) vs 唐纳德·特朗普 (共和党)", { 
  x: 1, y: 2.6, w: 7.5, h: 0.6, 
  fontSize: 18, color: "333333" 
});
slide1.addText("选举人团制度: 538张选举人票, 270票即可获胜", { 
  x: 1, y: 3.4, w: 7.5, h: 0.6, 
  fontSize: 18, color: "333333" 
});
slide1.addText("关键摇摆州: 宾夕法尼亚、密歇根、威斯康星、乔治亚、亚利桑那、内华达", { 
  x: 1, y: 4.2, w: 7.5, h: 1, 
  fontSize: 16, color: "666666" 
});

// 第2页: 选举结果与影响
let slide2 = pres.addSlide();
slide2.addText("2024年美国大选结果", { 
  x: 0.5, y: 0.5, w: 8.5, h: 1, 
  fontSize: 32, bold: true, color: "1E3A5F",
  align: "center" 
});
slide2.addText("唐纳德·特朗普获胜, 成为美国第47任总统", { 
  x: 1, y: 1.8, w: 7.5, h: 0.6, 
  fontSize: 18, color: "333333" 
});
slide2.addText("选举人票: 特朗普 312票 vs 哈里斯 226票", { 
  x: 1, y: 2.6, w: 7.5, h: 0.6, 
  fontSize: 18, color: "333333" 
});
slide2.addText("普选票: 特朗普约49.9% vs 哈里斯约48.3%", { 
  x: 1, y: 3.4, w: 7.5, h: 0.6, 
  fontSize: 18, color: "333333" 
});
slide2.addText("政策影响: 经济政策、移民政策、对外关系将面临重大调整", { 
  x: 1, y: 4.2, w: 7.5, h: 0.6, 
  fontSize: 16, color: "666666" 
});

// 保存文件
const outputPath = "/Users/admin/work/agent_loop/outputs/opencode_us_election_20260214_170709.pptx";
pres.writeFile({ fileName: outputPath })
  .then(() => {
    console.log("PPT生成成功:", outputPath);
  })
  .catch(err => {
    console.error("PPT生成失败:", err);
    process.exit(1);
  });
