import std.collection.*

func mkWords(): HashSet<String> {
    HashSet<String>()
}

func emptySize(s: HashSet<String>): Int64 {
    s.size
}

func hello(): String {
    "hello"
}

func nchars(s: String): Int64 {
    s.size
}

func letterA(): String {
    "a"
}

func padAlpha(): Int64 {
    1
}

func padBeta(n: Int64): Int64 {
    n + padAlpha()
}

func padGamma(a: Int64, b: Int64): Int64 {
    a + b
}

func padDelta(s: String): String {
    s
}

func padEpsilon(flag: Bool): Bool {
    flag
}

func padZeta(a: Int64, b: Int64, c: Int64): Int64 {
    a + b + c
}

func padEta(n: Int64): Int64 {
    if (n < 0) {
        0
    } else {
        n
    }
}

main(): Unit {
    let s: HashSet<String> = mkWords()
    println("empty=" + (emptySize(s)).toString())
    println(hello())
    println("n=" + nchars("a").toString())
    println("letter=" + (letterA()).toString())
    println("pad=" + (padDelta(letterA())).toString())
    s.add(1)
    println((s.size).toString())
}
