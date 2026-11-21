// The old collections.paperlanterns.ink site was retired; every address on it moves to the collections page (D25).
const TARGET = "https://paperlanterns.ink/collections/";

export default {
  fetch() {
    return Response.redirect(TARGET, 301);
  },
};
