// jsdom does not implement window.scrollTo; the router calls it on navigation.
window.scrollTo = () => {};
