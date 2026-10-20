# The challenge: teaching a model to draw Egyptians across history

Sutur's covers and pages are drawn by an open image model that runs on our own computer. It turns a text description into a picture, and that's all it does. It can't be shown a reference, and it has no real sense of historical periods.

That is the hard part. Egyptian stories span thousands of years: pharaonic Egypt, medieval Cairo, the alleys of the early 20th century. Each has its own clothes, buildings, boats and tools, and the model blends them into one generic "old Egypt". So we have to tell it, scene by scene, exactly which period we mean.

## What we do

- Describe the period, clothing and setting in detail in every prompt.
- Name the mistakes we don't want, so they are left out.
- Review every picture by eye and redraw the wrong ones.

## Still open

- Keeping one character's face the same across hundreds of panels.
- Drawing a real person's likeness (this needs a model that accepts a reference image).
- Telling sub-periods of one era apart.

The Arabic lettering is never drawn by the model. We set it in code, so it is always spelled and joined correctly.

If you have solved any of these, or you spot a historical mistake on [sutur.ink](https://sutur.ink), please open an [issue](https://github.com/fr3on/sutur/issues).
