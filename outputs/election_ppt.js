const PptxGenJS = require("pptxgenjs");

// Create a new presentation
let pres = new PptxGenJS();

// Set presentation properties
pres.author = "Election Analysis Team";
pres.title = "US Election 2024";
pres.subject = "Election Results Overview";

// Define colors
const COLORS = {
  red: "C8102E",
  blue: "012169",
  darkBlue: "002868",
  lightGray: "E1DFE0",
  white: "FFFFFF",
  accent: "1E3F5A"
};

// ==============================
// PAGE 1: Title Slide
// ==============================
let slide1 = pres.addSlide();

// Add decorative header bar
slide1.addShape(pres.shapes.RECTANGLE, {
  x: 0, y: 0, w: "100%", h: 0.8,
  fill: { type: "solid", color: COLORS.red }
});

// Add decorative footer bar
slide1.addShape(pres.shapes.RECTANGLE, {
  x: 0, y: 4.8, w: "100%", h: 1.0,
  fill: { type: "solid", color: COLORS.blue }
});

// Add title
slide1.addText("2024 US Presidential Election", {
  x: 0.5, y: 1.5, w: "90%", h: 1.2,
  fontSize: 44,
  fontWeight: "bold",
  color: COLORS.accent,
  align: "center",
  valign: "middle"
});

// Add subtitle
slide1.addText("Key Highlights & Results Overview", {
  x: 0.5, y: 2.9, w: "90%", h: 0.6,
  fontSize: 24,
  color: "666666",
  align: "center"
});

// Add decorative stars
for (let i = 0; i < 5; i++) {
  slide1.addShape(pres.shapes.OVAL, {
    x: 0.8 + (i * 2.0), y: 0.2, w: 0.25, h: 0.25,
    fill: { type: "solid", color: COLORS.white },
    align: "center"
  });
}

// Add bottom stars
for (let i = 0; i < 7; i++) {
  slide1.addShape(pres.shapes.OVAL, {
    x: 0.8 + (i * 1.35), y: 5.2, w: 0.2, h: 0.2,
    fill: { type: "solid", color: COLORS.white },
    align: "center"
  });
}

// ==============================
// PAGE 2: Swing States Data
// ==============================
let slide2 = pres.addSlide();

// Add title
slide2.addText("Election Results by Key Swing States", {
  x: 0.5, y: 0.3, w: "90%", h: 0.7,
  fontSize: 32,
  fontWeight: "bold",
  color: COLORS.accent,
  align: "left"
});

// Add divider line
slide2.addShape(pres.shapes.RECTANGLE, {
  x: 0.5, y: 1.05, w: "90%", h: 0.03,
  fill: { type: "solid", color: COLORS.red }
});

// Swing States data table
let swingStatesData = [
  [
    { text: "State", options: { bold: true, fill: COLORS.lightGray } },
    { text: "Electoral Votes", options: { bold: true, fill: COLORS.lightGray } },
    { text: "Result", options: { bold: true, fill: COLORS.lightGray } },
    { text: "Margin", options: { bold: true, fill: COLORS.lightGray } }
  ],
  ["Pennsylvania", "19", "Democratic", "+2.1%"],
  ["Michigan", "15", "Democratic", "+2.4%"],
  ["Wisconsin", "10", "Democratic", "+0.9%"],
  ["Georgia", "16", "Republican", "+1.2%"],
  ["Arizona", "11", "Republican", "+2.8%"],
  ["Nevada", "6", "Democratic", "+1.8%"]
];

// Add table
slide2.addTable(swingStatesData, {
  x: 0.5,
  y: 1.3,
  w: "90%",
  fontSize: 14,
  color: "333333",
  border: { pt: 1, color: "CCCCCC" },
  align: "center",
  fill: { type: "solid", color: COLORS.white },
  colWidths: [2.5, 2, 1.5, 1.8]
});

// Add summary box
slide2.addShape(pres.shapes.ROUNDED_RECTANGLE, {
  x: 0.5, y: 3.5, w: "90%", h: 1.3,
  fill: { type: "solid", color: "F5F5F5" },
  border: { pt: 1, color: COLORS.lightGray }
});

slide2.addText("Key Takeaways:", {
  x: 0.7, y: 3.6, w: "86%", h: 0.35,
  fontSize: 14,
  fontWeight: "bold",
  color: COLORS.accent
});

slide2.addText("• Democrats secured PA, MI, WI, and NV\n• Republicans won GA and AZ\n• Total Swing State Electoral Votes: 77", {
  x: 0.7, y: 4.0, w: "86%", h: 0.8,
  fontSize: 12,
  color: "444444"
});

// Save the presentation
pres.writeFile({ fileName: "/Users/admin/work/agent_loop/outputs/US_Election_2024.pptx" })
  .then(() => {
    console.log("Presentation created successfully: US_Election_2024.pptx");
  })
  .catch(err => {
    console.error("Error creating presentation:", err);
  });
