// Positions inside the real "Why?" sheet capture (m-*-why.png, 390x844 css px). Re-measured on the 24 Nov capture (word boxes read from the PNG, css px); the sheet's
// layout is fixed by frontend/app.css, so these only need re-measuring if the sheet's text blocks change.
export const WHY = {
  panelTop: 411,
  lead: { x: 348, y: 476 }, // just right of "(about 1 in 44 riders)," (the line ends near x 338)
  people: { x: 382, y: 684 }, // just right of "about 27 to 50" (the line ends near x 372)
  seats: { x: 400, y: 706 }, // on the bezel just outside the sheet, right of "has 35" (the text reaches the edge at x 390)
  rated: { x: 268, y: 728 }, // just right of "rated for 63 people." (the line ends near x 255)
  focus: { x: 195, y: 640 },
};
