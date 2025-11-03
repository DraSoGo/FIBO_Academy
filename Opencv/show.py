import numpy as np
import matplotlib.pyplot as plt

# ข้อมูล
A = np.array([
    -50,-50,-50,-50,-50,80,5.2,6.7,9.3,10.1,12.3,13.5,15.3,17.1,18.2,55.0,
    21.0,22.8,24.3,24.1,26.1,26.6,28.1,28.5,29.8,29.6,29.5,29.8,28.2,28.0,
    27.8,26.1,24.2,23.9,23.3,21.3,19.9,18.5,4.0,15.8,14.7,12.1,10.5,8.4,80,
    -50,-50,-50,-50,-50
])
A += 50
# แกน x เป็นดัชนีของข้อมูล
x = np.arange(len(A))

# วาดกราฟ
plt.figure(figsize=(10,4))
plt.plot(x, A, marker='o')
plt.title('Dough')
plt.xlabel('Time')
plt.ylabel('High')
plt.grid(True, linestyle='--', alpha=0.5)
plt.tight_layout()
plt.show()