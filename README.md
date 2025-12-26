## Snake Game 2D

Colourful, modern 2D Snake with smooth movement, animated food, scoring, and top-5 high scores.

### Controls

- **Move**: Arrow keys or WASD  
- **Pause**: P  
- **Restart**: R  
- **High scores**: H  
- **Quit**: Esc

### Install (macOS)

Requires **Python 3.10+**.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Run

```bash
source .venv/bin/activate
python main.py
```

### Notes

- **Score**: +10 points per food.
- **Game over**: if the snake hits **itself** (or a wall).
- **High scores**: saved locally to `highscores.json`, only **top 5** are displayed in-game.


