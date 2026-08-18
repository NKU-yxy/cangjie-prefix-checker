import std.collection.*

func tinyMap(): HashMap<String, Int64> {
    let m: HashMap<String, Int64> = HashMap<String, Int64>()
    m.add("a", 1)
    m
}

func mapLen(m: HashMap<String, Int64>): Int64 {
    m.size
}

func keyA(): String {
    "a"
}

func val1(): Int64 {
    1
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
    let m: HashMap<String, Int64> = tinyMap()
    println("len=" + (mapLen(m)).toString())
    println("key=" + (keyA()).toString())
    println("val=" + (val1()).toString())
    println("pad=" + (padAlpha()).toString())
    let out: Int64 = m.get(1)
    println((out).toString())
}
