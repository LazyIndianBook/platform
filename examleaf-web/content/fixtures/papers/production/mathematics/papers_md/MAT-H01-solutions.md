# MATHEMATICS — Solutions to Practice Paper MAT-H01

### 1(a)
**Ans.** No; $R=\{(0,0)\}$ only, so e.g. $(1,1)\notin R$ since $1^2+1^2=2\neq0$ *(1)*

### 1(b)
**Ans.** $^5P_3 = 60$ *(1)*

### 1(c)
**Ans.** (iii) $(A^{-1})'$, since $(A^{-1})'A' = (AA^{-1})' = I' = I$ and $A'(A^{-1})' = (A^{-1}A)' = I$ *(1)*

### 1(d)
**Ans.** $2\times12$ *(1)*

### 1(e)
**Ans.** False *(1)*

### 1(f)
**Ans.** (ii) $\dfrac1e$ *(1)*

### 1(g)
**Ans.** $\log y=\log(1+x)+\log(1+x^2)+\log(1+x^4)$, so $\dfrac1y\dfrac{dy}{dx}=\dfrac{1}{1+x}+\dfrac{2x}{1+x^2}+\dfrac{4x^3}{1+x^4}$ *(1)*

### 1(h)
**Ans.** $1$ *(1)*

### 1(i)
**Ans.** $\dfrac16\tan^{-1}\dfrac{3x}{2}+C$ *(1)*

### 1(j)
**Ans.** (ii) 2 *(1)*

### 1(k)
**Ans.** True *(1)*

### 1(l)
**Ans.** (i) $0,\dfrac12,\dfrac{\sqrt3}2$ *(1)*

### 2
| Step | Marks |
|---|---|
| The images $4,1,2,3$ are all distinct and cover $\{1,2,3,4\}$, so $f$ is one-one and onto, i.e. invertible | ½ |
| $f^{-1}=\{(4,1),(1,2),(2,3),(3,4)\}=\{(1,2),(2,3),(3,4),(4,1)\}$ | ½ |
| $(f\circ f)(1)=f(4)=3$, $(f\circ f)(2)=f(1)=4$, $(f\circ f)(3)=f(2)=1$, $(f\circ f)(4)=f(3)=2$ | ½ |
| $(f\circ f\circ f)(1)=f(3)=2$, $(f\circ f\circ f)(2)=f(4)=3$, $(f\circ f\circ f)(3)=f(1)=4$, $(f\circ f\circ f)(4)=f(2)=1$; so $f\circ f\circ f=\{(1,2),(2,3),(3,4),(4,1)\}=f^{-1}$ | ½ |
| **Total** | **2** |

**Final answer:** $f^{-1}=\{(1,2),(2,3),(3,4),(4,1)\}=f\circ f\circ f$

### 2 OR
| Step | Marks |
|---|---|
| One-one: $2x_1^3-1=2x_2^3-1 \Rightarrow x_1^3=x_2^3 \Rightarrow (x_1-x_2)(x_1^2+x_1x_2+x_2^2)=0$; the second factor vanishes only at $x_1=x_2=0$, so in every case $x_1=x_2$ | 1 |
| Onto: for any $y \in \mathbf R$, $x=\left(\dfrac{y+1}{2}\right)^{1/3} \in \mathbf R$ and $f(x)=y$ | 1 |
| **Total** | **2** |

**Final answer:** $f$ is one-one and onto.

### 3
| Step | Marks |
|---|---|
| $A' = P' + Q' = P - Q$, so $Q = \tfrac12(A - A')$; $A' = \begin{bmatrix} 3 & 4 & 2 \\ -2 & 0 & 5 \\ 1 & -1 & 3 \end{bmatrix}$ | 1 |
| $Q = \tfrac12\begin{bmatrix} 0 & -6 & -1 \\ 6 & 0 & -6 \\ 1 & 6 & 0 \end{bmatrix} = \begin{bmatrix} 0 & -3 & -\tfrac12 \\ 3 & 0 & -3 \\ \tfrac12 & 3 & 0 \end{bmatrix}$ | 1 |
| **Total** | **2** |

**Final answer:** $Q = \begin{bmatrix} 0 & -3 & -\tfrac12 \\ 3 & 0 & -3 \\ \tfrac12 & 3 & 0 \end{bmatrix}$

### 4
| Step | Marks |
|---|---|
| $\dfrac{dy}{dx}=-A\sin x+B\cos x$; $\dfrac{d^2y}{dx^2}=-A\cos x-B\sin x=-y$ | 1 |
| $\Rightarrow\dfrac{d^2y}{dx^2}+y=0$ | 1 |
| **Total** | **2** |

**Final answer:** verified

### 5
| Step | Marks |
|---|---|
| $S = 4\pi r^2 \Rightarrow \dfrac{dS}{dt} = 8\pi r\,\dfrac{dr}{dt}$ | 1 |
| $\dfrac{dS}{dt} = 8\pi(6)\left(\dfrac15\right) = \dfrac{48\pi}{5}$ | 1 |
| **Total** | **2** |

**Final answer:** $\dfrac{48\pi}{5}$ cm²/s

### 6
| Step | Marks |
|---|---|
| Put $t=\sqrt x$, so $x=t^2$, $dx=2t\,dt$; $\dfrac{1}{\sqrt x+x}=\dfrac{1}{t(1+t)}$ | 1 |
| $\displaystyle\int\dfrac{2t\,dt}{t(1+t)}=2\displaystyle\int\dfrac{dt}{1+t}=2\log(1+t)+C$ | 1 |
| **Total** | **2** |

**Final answer:** $2\log(1+\sqrt x)+C$

### 6 OR
| Step | Marks |
|---|---|
| $\dfrac{x}{(x-2)^2}=\dfrac{1}{x-2}+\dfrac{2}{(x-2)^2}$ (write $x=(x-2)+2$) | 1 |
| $\displaystyle\int = \log\lvert x-2\rvert-\dfrac{2}{x-2}+C$ | 1 |
| **Total** | **2** |

**Final answer:** $\log\lvert x-2\rvert-\dfrac{2}{x-2}+C$

### 7
| Step | Marks |
|---|---|
| By parts, $u=\sin^{-1}x$, $dv=dx$: $\displaystyle\int\sin^{-1}x\,dx=x\sin^{-1}x-\displaystyle\int\dfrac{x}{\sqrt{1-x^2}}\,dx$ | 1 |
| $\displaystyle\int\dfrac{x\,dx}{\sqrt{1-x^2}}=-\sqrt{1-x^2}$, so the integral $=x\sin^{-1}x+\sqrt{1-x^2}+C$ | 1 |
| **Total** | **2** |

**Final answer:** $x\sin^{-1}x+\sqrt{1-x^2}+C$

### 8
| Step | Marks |
|---|---|
| Let $\vec a,\vec b,\vec c$ be the position vectors of $A,B,C$; the centroid $G$ has position vector $\vec g=\dfrac{\vec a+\vec b+\vec c}{3}$ | 1 |
| $\vec{GA}+\vec{GB}+\vec{GC}=(\vec a-\vec g)+(\vec b-\vec g)+(\vec c-\vec g)=(\vec a+\vec b+\vec c)-3\vec g=\vec 0$ | 1 |
| **Total** | **2** |

**Final answer:** $\vec{GA}+\vec{GB}+\vec{GC}=\vec 0$

### 9
| Step | Marks |
|---|---|
| $\lvert\hat a-\hat b\rvert^2=\lvert\hat a\rvert^2+\lvert\hat b\rvert^2-2\hat a\cdot\hat b=2-2\cos\dfrac\pi3$ | 1 |
| $=2-1=1\Rightarrow\lvert\hat a-\hat b\rvert=1$ | 1 |
| **Total** | **2** |

**Final answer:** $1$

### 10
| Step | Marks |
|---|---|
| $E(X)=-1\times\dfrac14+0\times\dfrac12+1\times\dfrac14=0$ | 1 |
| $E(X^2)=1\times\dfrac14+0\times\dfrac12+1\times\dfrac14=\dfrac12$; $\operatorname{Var}(X)=E(X^2)-[E(X)]^2=\dfrac12-0$ | 1 |
| **Total** | **2** |

**Final answer:** $\dfrac12$

### 10 OR
| Step | Marks |
|---|---|
| $B$: first throw $\in\{2,4,6\}$, 18 of the 36 outcomes, $P(B)=\dfrac{18}{36}$ | 1 |
| $A\cap B$: first throw even and second throw odd, $3\times3=9$ outcomes; $P(A\mid B)=\dfrac{P(A\cap B)}{P(B)}=\dfrac{9/36}{18/36}$ | 1 |
| **Total** | **2** |

**Final answer:** $\dfrac12$

### 11
| Step | Marks |
|---|---|
| $\frac{3\pi}5\notin\left[-\frac{\pi}2,\frac{\pi}2\right]$; $\sin\frac{3\pi}5=\sin\left(\pi-\frac{3\pi}5\right)=\sin\frac{2\pi}5$, and $\frac{2\pi}5\in\left[-\frac{\pi}2,\frac{\pi}2\right]$, so $\sin^{-1}\left(\sin\frac{3\pi}5\right)=\frac{2\pi}5$ | 1 |
| $\frac{7\pi}5\notin[0,\pi]$; $\cos\frac{7\pi}5=\cos\left(2\pi-\frac{7\pi}5\right)=\cos\frac{3\pi}5$, and $\frac{3\pi}5\in[0,\pi]$, so $\cos^{-1}\left(\cos\frac{7\pi}5\right)=\frac{3\pi}5$ | 1 |
| $\tan$ has period $\pi$: $\tan\frac{9\pi}5=\tan\left(\frac{9\pi}5-2\pi\right)=\tan\left(-\frac{\pi}5\right)$, and $-\frac{\pi}5\in\left(-\frac{\pi}2,\frac{\pi}2\right)$, so $\tan^{-1}\left(\tan\frac{9\pi}5\right)=-\frac{\pi}5$ | 1 |
| Value $=\dfrac{2\pi}5+\dfrac{3\pi}5-\dfrac{\pi}5=\dfrac{4\pi}5$ | 1 |
| **Total** | **4** |

**Final answer:** $\dfrac{4\pi}5$

### 11 OR
| Step | Marks |
|---|---|
| Let $A=\sin^{-1}\frac{24}{25}$, so $\sin A=\frac{24}{25},\cos A=\frac7{25},\tan A=\frac{24}7$ ($A\in(0,\frac{\pi}2)$); let $B=\cos^{-1}\frac45$, so $\cos B=\frac45,\sin B=\frac35,\tan B=\frac34$ ($B\in(0,\frac{\pi}2)$) | 1 |
| $\tan(A+B)=\dfrac{\tan A+\tan B}{1-\tan A\tan B}=\dfrac{\frac{24}7+\frac34}{1-\frac{24}7\cdot\frac34}=\dfrac{117/28}{1-72/28}=\dfrac{117/28}{-44/28}=-\dfrac{117}{44}$ | 2 |
| $\sin A=\frac{24}{25}>\frac45=\cos B\Rightarrow A+B>\frac{\pi}2$; with $A+B\in\left(\frac{\pi}2,\pi\right)$ and $\tan(A+B)=-\frac{117}{44}$, $A+B=\pi-\tan^{-1}\frac{117}{44}$, i.e. $A+B+\tan^{-1}\frac{117}{44}=\pi$ | 1 |
| **Total** | **4** |

### 12
| Step | Marks |
|---|---|
| $\log x=\dfrac12\tan^{-1}t\,\log a\Rightarrow\dfrac1x\dfrac{dx}{dt}=\dfrac{\log a}{2(1+t^2)}$ | 2 |
| $\log y=\dfrac12\cot^{-1}t\,\log a\Rightarrow\dfrac1y\dfrac{dy}{dt}=-\dfrac{\log a}{2(1+t^2)}$ | 1 |
| $\dfrac{dy}{dx}=\dfrac{dy/dt}{dx/dt}=\dfrac{-y\log a}{x\log a}=-\dfrac{y}{x}$ (the factor $2(1+t^2)$ cancels) | 1 |
| **Total** | **4** |

**Final answer:** verified

### 13
| Step | Marks |
|---|---|
| $x^2-4x+3=(x-1)(x-3)$: positive on $[0,1]$, negative on $[1,3]$ | 1 |
| $\displaystyle\int_0^1(x^2-4x+3)\,dx=\left[\dfrac{x^3}{3}-2x^2+3x\right]_0^1=\dfrac43$ | 1 |
| $\displaystyle\int_1^3-(x^2-4x+3)\,dx=-\left[\dfrac{x^3}{3}-2x^2+3x\right]_1^3=-\left(0-\dfrac43\right)=\dfrac43$ | 1 |
| Sum $=\dfrac43+\dfrac43=\dfrac83$ | 1 |
| **Total** | **4** |

**Final answer:** $\dfrac83$

### 13 OR
| Step | Marks |
|---|---|
| (a) By the fundamental theorem with the chain rule, $F'(x)=(3x^4+1)\cdot 2x$ | 1 |
| $F'(2)=(48+1)\cdot4=196$ | 1 |
| (b) Put $u=x+\dfrac1x$, $du=\left(1-\dfrac1{x^2}\right)dx$; limits $x=1\Rightarrow u=2$, $x=2\Rightarrow u=\dfrac52$ | 1 |
| $\displaystyle\int_2^{5/2}e^u\,du=\left[e^u\right]_2^{5/2}=e^{5/2}-e^2$ | 1 |
| **Total** | **4** |

**Final answer:** (a) $196$; (b) $e^{5/2}-e^2$

### 14
| Step | Marks |
|---|---|
| Smaller part (right of $x=6$) is symmetric about the $x$-axis: area $=2\displaystyle\int_6^{12}\sqrt{144-x^2}\,dx$ | 1 |
| $\displaystyle\int\sqrt{144-x^2}\,dx=\dfrac x2\sqrt{144-x^2}+72\sin^{-1}\dfrac x{12}$ | 1 |
| At $x=12$: $0+72\times\dfrac\pi2=36\pi$. At $x=6$: $3\sqrt{108}+72\times\dfrac\pi6=18\sqrt3+12\pi$ | 1 |
| $\displaystyle\int_6^{12}=36\pi-18\sqrt3-12\pi=24\pi-18\sqrt3$; area $=2(24\pi-18\sqrt3)=48\pi-36\sqrt3$ square units | 1 |
| **Total** | **4** |

> *Diagram expected:* circle of radius 12, chord $x=6$ drawn, the smaller region (right of the chord) shaded.

**Final answer:** $48\pi-36\sqrt3$ square units.

### 14 OR
| Step | Marks |
|---|---|
| $y=\dfrac35\sqrt{100-x^2}$; smaller part (right of $x=5$) area $=2\times\dfrac35\displaystyle\int_5^{10}\sqrt{100-x^2}\,dx$ | 1 |
| $\displaystyle\int\sqrt{100-x^2}\,dx=\dfrac x2\sqrt{100-x^2}+50\sin^{-1}\dfrac x{10}$ | 1 |
| At $x=10$: $50\times\dfrac\pi2=25\pi$. At $x=5$: $\dfrac52\sqrt{75}+50\times\dfrac\pi6=\dfrac{25\sqrt3}2+\dfrac{25\pi}3$ | 1 |
| $\displaystyle\int_5^{10}=25\pi-\dfrac{25\sqrt3}2-\dfrac{25\pi}3=\dfrac{50\pi}3-\dfrac{25\sqrt3}2$; area $=\dfrac65\left(\dfrac{50\pi}3-\dfrac{25\sqrt3}2\right)=20\pi-15\sqrt3$ square units | 1 |
| **Total** | **4** |

> *Diagram expected:* ellipse with semi-axes 10 and 6, chord $x=5$ drawn, the smaller region shaded.

**Final answer:** $20\pi-15\sqrt3$ square units.

### 15
| Step | Marks |
|---|---|
| $\dfrac{dy}{dx}=\dfrac{y^2+2xy}{x^2}$ (homogeneous); put $y=vx$, $\dfrac{dy}{dx}=v+x\dfrac{dv}{dx}$ | 1 |
| $v+x\dfrac{dv}{dx}=v^2+2v\Rightarrow x\dfrac{dv}{dx}=v^2+v$ | 1 |
| $\left(\dfrac1v-\dfrac1{v+1}\right)dv=\dfrac{dx}{x}\Rightarrow\log\left\lvert\dfrac{v}{v+1}\right\rvert=\log\lvert x\rvert+\log\lvert C\rvert\Rightarrow\dfrac{v}{v+1}=Cx$ | 1 |
| Put $v=\dfrac{y}{x}$: $\dfrac{y}{x+y}=Cx$; at $(1,1)$, $C=\dfrac12$, so $2y=x(x+y)$ | 1 |
| **Total** | **4** |

**Final answer:** $y=\dfrac{x^2}{2-x}$

### 15 OR
| Step | Marks |
|---|---|
| $\dfrac{d}{dt}\left(4\pi r^2\right)=k$ (constant) | 1 |
| Integrating: $4\pi r^2=kt+C$ | 1 |
| $t=0,\ r=1\Rightarrow C=4\pi$; $t=3,\ r=2\Rightarrow 16\pi=3k+4\pi\Rightarrow k=4\pi$ | 1 |
| $4\pi r^2=4\pi t+4\pi\Rightarrow r^2=t+1$ | 1 |
| **Total** | **4** |

**Final answer:** $r=\sqrt{t+1}$ units

### 16
| Step | Marks |
|---|---|
| $\vec{AB}=\hat i-2\hat j+3\hat k$, $\lvert\vec{AB}\rvert=\sqrt{14}$; direction cosines $=\dfrac1{\sqrt{14}},-\dfrac2{\sqrt{14}},\dfrac3{\sqrt{14}}$ | 1 |
| $\vec{AC}=\hat i-\hat j+3\hat k$, $\lvert\vec{AC}\rvert=\sqrt{11}$; direction cosines $=\dfrac1{\sqrt{11}},-\dfrac1{\sqrt{11}},\dfrac3{\sqrt{11}}$ | 1 |
| $\cos A=l_1l_2+m_1m_2+n_1n_2=\dfrac{(1)(1)+(-2)(-1)+(3)(3)}{\sqrt{14}\,\sqrt{11}}=\dfrac{12}{\sqrt{154}}$ | 1 |
| $\cos A\ne0$, so $\angle A$ is not a right angle | 1 |
| **Total** | **4** |

**Final answer:** d.c.s of $\vec{AB}$: $\dfrac1{\sqrt{14}},-\dfrac2{\sqrt{14}},\dfrac3{\sqrt{14}}$; of $\vec{AC}$: $\dfrac1{\sqrt{11}},-\dfrac1{\sqrt{11}},\dfrac3{\sqrt{11}}$; $\angle A$ is not a right angle

### 17
| Step | Marks |
|---|---|
| Let $E_1$: the first ball is red, $E_2$: the first ball is black, $A$: the second ball is red. $P(E_1)=\dfrac58$, $P(E_2)=\dfrac38$; $P(A\mid E_1)=\dfrac47$, $P(A\mid E_2)=\dfrac57$ | 1 |
| By the theorem of total probability, $P(A)=\dfrac58\times\dfrac47+\dfrac38\times\dfrac57=\dfrac{20}{56}+\dfrac{15}{56}=\dfrac{35}{56}=\dfrac58$ | 1 |
| By Bayes' theorem, $P(E_2\mid A)=\dfrac{P(E_2)P(A\mid E_2)}{P(A)}=\dfrac{15/56}{35/56}$ | 1 |
| $=\dfrac{15}{35}=\dfrac37$ | 1 |
| **Total** | **4** |

**Final answer:** $\dfrac58$ and $\dfrac37$

### 17 OR
| Step | Marks |
|---|---|
| $P(A\text{ fails})=\dfrac12$, $P(B\text{ fails})=\dfrac23$, $P(C\text{ fails})=\dfrac34$; $P(\text{none solves})=\dfrac12\times\dfrac23\times\dfrac34=\dfrac14$ | 1 |
| (i) $P(\text{at least one})=1-\dfrac14$ | 1 |
| (ii) $P(\text{exactly one})=\dfrac12\cdot\dfrac23\cdot\dfrac34+\dfrac12\cdot\dfrac13\cdot\dfrac34+\dfrac12\cdot\dfrac23\cdot\dfrac14$ | 1 |
| $=\dfrac{6}{24}+\dfrac{3}{24}+\dfrac{2}{24}=\dfrac{11}{24}$ | 1 |
| **Total** | **4** |

**Final answer:** (i) $\dfrac34$ (ii) $\dfrac{11}{24}$

### 18
| Step | Marks |
|---|---|
| $AX=B$ with $A=\begin{pmatrix}3&-3&4\\1&4&2\\1&-2&-3\end{pmatrix}$, $B=\begin{pmatrix}19\\-8\\5\end{pmatrix}$; $\lvert A\rvert=3(-8)+3(-5)+4(-6)=-24-15-24=-63\neq0$ | 1 |
| Cofactors: $A_{11}=-8,\ A_{12}=5,\ A_{13}=-6,\ A_{21}=-17,\ A_{22}=-13,\ A_{23}=3,\ A_{31}=-22,\ A_{32}=-2,\ A_{33}=15$ | 2 |
| $\operatorname{adj}A=\begin{pmatrix}-8&-17&-22\\5&-13&-2\\-6&3&15\end{pmatrix}$, $A^{-1}=-\dfrac{1}{63}\operatorname{adj}A$ | 1 |
| $X=A^{-1}B=-\dfrac{1}{63}\begin{pmatrix}(-8)(19)+(-17)(-8)+(-22)(5)\\5(19)+(-13)(-8)+(-2)(5)\\(-6)(19)+3(-8)+15(5)\end{pmatrix}=-\dfrac{1}{63}\begin{pmatrix}-126\\189\\-63\end{pmatrix}$ | 1 |
| $x=2,\ y=-3,\ z=1$ | 1 |
| **Total** | **6** |

**Final answer:** $x=2,\ y=-3,\ z=1$.

### 18 OR
| Step | Marks |
|---|---|
| $\lvert A\rvert=\lambda(\lambda-2)-1(1-2)+1(2-2\lambda)=\lambda^2-4\lambda+3$ | 1 |
| $A$ is singular when $\lvert A\rvert=0$: $(\lambda-1)(\lambda-3)=0$, so $\lambda=1$ or $\lambda=3$ | 1 |
| For $\lambda=2$: $A=\begin{pmatrix}2&1&1\\1&2&1\\2&2&1\end{pmatrix}$, $\lvert A\rvert=4-8+3=-1\neq0$ | ½ |
| Cofactors: $A_{11}=0,\ A_{12}=1,\ A_{13}=-2,\ A_{21}=1,\ A_{22}=0,\ A_{23}=-2,\ A_{31}=-1,\ A_{32}=-1,\ A_{33}=3$ | 2 |
| $\operatorname{adj}A=\begin{pmatrix}0&1&-1\\1&0&-1\\-2&-2&3\end{pmatrix}$ | ½ |
| $A^{-1}=\dfrac{1}{\lvert A\rvert}\operatorname{adj}A=-\operatorname{adj}A=\begin{pmatrix}0&-1&1\\-1&0&1\\2&2&-3\end{pmatrix}$ | 1 |
| **Total** | **6** |

**Final answer:** $\lambda=1$ or $\lambda=3$; for $\lambda=2$, $A^{-1}=\begin{pmatrix}0&-1&1\\-1&0&1\\2&2&-3\end{pmatrix}$.

### 19
| Step | Marks |
|---|---|
| A general point on the curve is $\left(\dfrac{y^2}{4}, y\right)$; $D^2 = \left(\dfrac{y^2}{4}\right)^2 + (y-3)^2 = \dfrac{y^4}{16}+y^2-6y+9$ | 1½ |
| $\dfrac{d(D^2)}{dy} = \dfrac{y^3}{4}+2y-6 = 0 \Rightarrow y^3+8y-24=0$ | 1 |
| $y=2$ satisfies this (since $8+16-24=0$); factoring, $y^3+8y-24=(y-2)(y^2+2y+12)$, and $y^2+2y+12=0$ has no real root (discriminant $<0$), so $y=2$ is the only critical point | 1½ |
| $\dfrac{d^2(D^2)}{dy^2} = \dfrac{3y^2}{4}+2 = 5 > 0$ at $y=2$, so $D^2$, and hence $D$, is least there | 1 |
| At $y=2$: $x=1$, and $D^2 = \dfrac{16}{16}+4-12+9=2$, so $D=\sqrt2$ | 1 |
| **Total** | **6** |

**Final answer:** the point $(1, 2)$, at a least distance of $\sqrt2$ units

### 19 OR
| Step | Marks |
|---|---|
| $f'(x) = 4x^3-24x^2+44x-24 = 4(x^3-6x^2+11x-6)$ | 1½ |
| $x^3-6x^2+11x-6 = (x-1)(x-2)(x-3)$, so $f'(x)=4(x-1)(x-2)(x-3)$ | 1½ |
| Sign of $f'(x)$: negative for $x<1$; positive for $1<x<2$; negative for $2<x<3$; positive for $x>3$ | 2 |
| Increasing on $(1,2)\cup(3,\infty)$ | ½ |
| Decreasing on $(-\infty,1)\cup(2,3)$ | ½ |
| **Total** | **6** |

**Final answer:** increasing on $(1,2)\cup(3,\infty)$; decreasing on $(-\infty,1)\cup(2,3)$

### 20
| Step | Marks |
|---|---|
| First line: $\vec r=(\hat i+2\hat j-3\hat k)+t(\hat i-\hat j+2\hat k)$; $\vec a_1=(1,2,-3)$, $\vec b_1=(1,-1,2)$ | 1 |
| Second line: $\vec r=(-\hat i+\hat j+2\hat k)+s(2\hat i+\hat j+\hat k)$; $\vec a_2=(-1,1,2)$, $\vec b_2=(2,1,1)$ | 1 |
| $\vec b_1\times\vec b_2=(-1-2,\,4-1,\,1+2)=(-3,3,3)$; $\lvert\vec b_1\times\vec b_2\rvert=\sqrt{9+9+9}=3\sqrt3$ | 2 |
| $\vec a_2-\vec a_1=(-2,-1,5)$; $(\vec a_2-\vec a_1)\cdot(\vec b_1\times\vec b_2)=6-3+15=18$ | 1 |
| $d=\dfrac{18}{3\sqrt3}=\dfrac6{\sqrt3}=2\sqrt3$ | 1 |
| **Total** | **6** |

**Final answer:** $d=2\sqrt3$

### 20 OR
| Step | Marks |
|---|---|
| Vector equation: $\vec r=(4\hat i-\hat j+2\hat k)+\lambda(\hat i-\hat j)$ | 1 |
| Any point of the line: $Q(4+\lambda,\,-1-\lambda,\,2)$ | 1 |
| $OQ^2=(4+\lambda)^2+(1+\lambda)^2+2^2=2\lambda^2+10\lambda+21$ | 1 |
| $2\lambda^2+10\lambda+21=9\Rightarrow\lambda^2+5\lambda+6=0$ | 1 |
| $(\lambda+2)(\lambda+3)=0\Rightarrow\lambda=-2$ or $\lambda=-3$ | 1 |
| Required points: $(2,1,2)$ and $(1,2,2)$ | 1 |
| **Total** | **6** |

**Final answer:** $\vec r=(4\hat i-\hat j+2\hat k)+\lambda(\hat i-\hat j)$; $(2,1,2)$ and $(1,2,2)$

### 21
| Step | Marks |
|---|---|
| Lines $x=9$, $x+y=11$, $2x+5y=40$ drawn in the first quadrant; bounded feasible region $OABCD$ shaded | 2 |
| Corners $O(0,0)$, $A(9,0)$, $B(9,2)$ (on $x=9$ and $x+y=11$), $C(5,6)$ (solving $x+y=11$ and $2x+5y=40$ together), $D(0,8)$ | 2 |
| $Z$ at $O,A,B,C,D$: $0, 27, 23, 3, -16$ | 1 |
| Maximum $Z = 27$ at $(9,0)$; minimum $Z = -16$ at $(0,8)$ | 1 |
| **Total** | **6** |

> *Diagram expected:* lines $x=9$, $x+y=11$ and $2x+5y=40$ with their intercepts; bounded feasible region $OABCD$ shaded; corners $O(0,0)$, $A(9,0)$, $B(9,2)$, $C(5,6)$, $D(0,8)$ labelled.

**Final answer:** Maximum $Z = 27$ at $x=9,y=0$; minimum $Z = -16$ at $x=0,y=8$.

### 21 OR
| Step | Marks |
|---|---|
| Lines $x+y=8$, $x+3y=12$, $3x+y=12$ drawn; unbounded feasible region (common to all three half-planes, first quadrant) shaded | 2 |
| Corners $A(0,12)$ (on $3x+y=12$), $B(2,6)$ (solving $x+y=8$ and $3x+y=12$ together), $C(6,2)$ (solving $x+y=8$ and $x+3y=12$ together), $D(12,0)$ (on $x+3y=12$) | 1 |
| $Z$ at $A,B,C,D$: $36, 22, 18, 24$; smallest $18$ at $C$ | 1 |
| Region unbounded: the half-plane $2x+3y<18$ has no point in common with it | 1 |
| Minimum $Z = 18$ at $(6,2)$ | 1 |
| **Total** | **6** |

> *Diagram expected:* lines $x+y=8$, $x+3y=12$ and $3x+y=12$ with their intercepts; unbounded feasible region (first quadrant, on or above all three lines) shaded; corners $A(0,12)$, $B(2,6)$, $C(6,2)$, $D(12,0)$ labelled; the line $2x+3y=18$ dotted.

**Final answer:** Minimum $Z = 18$ at $x = 6$, $y = 2$.

*Note:* without the half-plane check the minimum is not justified (−1).

