// Positions inside the real "Why?" sheet capture (m-*-why.png, 390x844 css px). Re-measured on the 24 Nov capture (word boxes read from the PNG, css px); the sheet's
// layout is fixed by frontend/app.css, so these only need re-measuring if the sheet's text blocks change.
export const WHY = {
  panelTop: 411,
  lead: { x: 262, y: 476 }, // "(about 1 in 44 riders)"
  people: { x: 328, y: 684 }, // just under "27 to 50" in "about 27 to 50 people on board" (the dot must not cover the numbers)
  seats: { x: 350, y: 706 }, // just under "has 35" in "The bus has 35 seats"
  rated: { x: 182, y: 728 }, // just under "63" in "rated for 63 people"
  focus: { x: 195, y: 640 },
};
