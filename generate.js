const pptxgen = require("pptxgenjs");
const html2pptx = require("/Users/admin/.claude/skills/pptx/scripts/html2pptx.js");
const fs = require("fs");

const outputDir = "/Users/admin/work/agent_loop/outputs";
if (!fs.existsSync(outputDir)) {
  fs.mkdirSync(outputDir, { recursive: true });
}

async function createPresentation() {
  const pres = new pptxgen();
  pres.layout = "LAYOUT_16x9";
  pres.title = "2024美国大选";
  pres.author = "OpenCode";

  const { slide: slide1 } = await html2pptx("/Users/admin/work/agent_loop/slide1.html", pres);
  const { slide: slide2 } = await html2pptx("/Users/admin/work/agent_loop/slide2.html", pres);

  const outputPath = "/Users/admin/work/agent_loop/outputs/oc_cli_us_election_20260214.pptx";
  await pres.writeFile({ fileName: outputPath });
  console.log("PPT生成成功:", outputPath);
}

createPresentation().catch(err => {
  console.error("PPT生成失败:", err);
  process.exit(1);
});
