const pptxgen = require('pptxgenjs');
const path = require('path');
const html2pptx = require('/Users/admin/.claude/skills/pptx/scripts/html2pptx');

async function createPresentation() {
  const pptx = new pptxgen();
  pptx.layout = 'LAYOUT_16x9';

  console.log('Processing slide 1...');
  const slide1 = await html2pptx('/Users/admin/work/agent_loop/slide1.html', pptx);

  console.log('Processing slide 2...');
  const slide2 = await html2pptx('/Users/admin/work/agent_loop/slide2.html', pptx);

  const outputPath = '/Users/admin/work/agent_loop/us_election_2pages.pptx';
  await pptx.writeFile(outputPath);
  console.log(`Presentation saved to: ${outputPath}`);
}

createPresentation().catch(console.error);
